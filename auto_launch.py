#!/bin/python3

import paramiko
import time
import fabric
import itertools
import signal
import sys

setenv = 'source /home/yidaz-nis/persist/gpgpusim-copy/setup_environment'
workingDirectory = '/home/yidaz-nis/persist/penny-mod/benchmark'

argNames = ['ICNT_MULT', 'WPQ_SIZE']
# argNames = ['PERSIST_BUFFER_SIZE', 'ICNT_MULT', 'INTERCONNECT_BUFFER_SIZE', 'WPQ_SIZE', 'ICNT_IN_SIZE', 'ICNT_OUT_SIZE']
# possibleTest = [
#     [50],
#     [32],
#     [50],
#     [4000000],
#     [64, 256, 4096, 8192, 32768],
# ]
possibleTest = [
    [1,2,4,8,32],
    [64,1024,4096]
]
workset = list(itertools.product(*possibleTest))
# workset = [
#     (50, 2, 50, 1024, 4096, 1024),
#     (50, 2, 50, 1024, 8192, 1024),
#     (50, 2, 50, 1024, 32768, 1024),
#     (50, 2, 50, 1024, 65536, 1024),
#     (50, 2, 50, 1024, 65536*2, 1024),
#     (50, 2, 50, 4096, 4096, 4096),
#     (50, 2, 50, 4096, 8192, 4096),
#     (50, 2, 50, 4096, 32768, 4096),
#     (50, 2, 50, 4096, 65536*2, 4096),
#     (50, 4, 50, 4096, 4096, 4096),
#     (50, 4, 50, 4096, 8192, 4096),
#     (50, 4, 50, 4096, 32768, 4096),
#     (50, 4, 50, 4096, 65536*2, 4096),
#         ]
dispatched = []

def alterCommand(parameter, number):
    return "sed -i '/{}/s/[0-9]\+/{}/g' /home/yidaz-nis/persist/penny-mod/benchmark/start_test_persist.sh".format(parameter, number)

def execute(channel: paramiko.Channel, cmd: str):
    cmd = cmd.strip() + '\n'
    result = ''
    channel.sendall(cmd)
    time.sleep(0.5)
    while channel.recv_ready() or not result.endswith('$ '):
        result += channel.recv(10240).decode('utf-8')
    result = result.replace('\r\n', '\n')
    result = '\n'.join(result.split('\n')[1:-1])
    return result

def runNext(channel: paramiko.Channel, server):
    if len(workset) == 0:
        return
    task = workset.pop()
    for index, i in enumerate(argNames):
        # if index == len(argNames) - 1:
        #     execute(channel, alterCommand(i, task[index - 1]))
        # else:
        execute(channel, alterCommand(i, task[index]))
    # execute(channel, './start_test_persist.sh P{}ICNT{}I{}WPQ{}IIN{}IOUT{} &'.format(task[0], task[1], task[2], task[3], task[4], task[5]))
    execute(channel, './start_test_persist.sh WPQFullICNT{}WPQ{} &'.format(task[0], task[1]))
    print('server{} :'.format(server))
    jobs = execute(channel, 'jobs')
    print(jobs)

proxyClient = paramiko.SSHClient()
proxyClient.set_missing_host_key_policy(paramiko.AutoAddPolicy())
proxyClient.connect('data.cs.purdue.edu', username='zhan3339', password='123ZYDzyd')
sshs = []
checks = []

for i in range(4):
    check = fabric.Connection('sushi{}'.format(i+1))
    check.run('ls', hide=True)
    checks.append(check)

    host = 'sushi{}.cs.purdue.edu'.format(i+1)
    proxy = proxyClient.get_transport().open_channel('direct-tcpip', (host, 22), ('data.cs.purdue.edu', 22))
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username='yidaz-nis', password='123ZYDzyd', sock=proxy)
    channel = ssh.invoke_shell()
    channel.sendall(setenv + '\n')
    channel.sendall('cd {}\n'.format(workingDirectory))
    while not channel.recv_ready():
        pass
    time.sleep(1)
    channel.recv(10240)
    print('{} connected'.format(host))
    sshs.append(channel)


command = "/home/yidaz-nis/local/usr/bin/mpstat -P ALL 1 1 | awk '/Average:/ && $2 ~ /[0-9]/ {print $3}'"
memCommand = "free -h | awk '/Mem:/'"

def signal_handler(sig, frame):
    print('Ctrl+C')
    for i in checks:
        i.close()
    for i in sshs:
        execute(i, "kill $(ps | egrep -v 'ssh|htop|bash' | awk '{print $1}')")
        i.close()
    sys.exit()

signal.signal(signal.SIGINT, signal_handler)

while True:
    for index, i in enumerate(checks):
        jobs = execute(sshs[index], 'jobs')
        print()
        print('server{} :'.format(index))
        print(jobs)
        out = i.run(command, hide=True).stdout.strip().split('\n')
        num = 0
        for l in out:
            if float(l) > 80:
                num += 1
        print('current busy processor: {}'.format(num))
        if num < 40:
            mem = float(i.run(memCommand, hide=True).stdout.strip().split()[2][:-1])
            print('current memory usage: {}G'.format(mem))
            if mem < 50:
                print('start next task')
                runNext(sshs[index], index)
    time.sleep(60*1)
