#!/usr/bin/env python3
import subprocess
import random

mullvad_list = subprocess.check_output(['mullvad', 'relay', 'list']).decode()
mullvad_list = mullvad_list.split('Brazil (br)')[-1].split('Bulgaria')[0].strip()
mullvad_list = mullvad_list.split('\n')
mullvad_list = [i.split(' ')[0].strip() for i in mullvad_list[1:]]
status = subprocess.check_output(['mullvad', 'status']).decode().strip()
try:
    status = status.split(' ')[2].strip()
except:
    subprocess.call(['mullvad', 'connect'])
    msg = 'Connectando ao VPN'
    subprocess.call(['notify-send', msg])

    
relay_choice = random.choice([i for i in mullvad_list if status not in i])
subprocess.check_output(['mullvad', 'relay', 'set', 'location', relay_choice])
subprocess.call(['mullvad', 'disconnect'])
subprocess.call(['mullvad', 'connect'])
msg = 'Mudando para {0}'.format(relay_choice)
subprocess.call(['notify-send', msg])
print(msg)
