#!/usr/bin/env python3
import argparse
import subprocess
import platform
import zipfile
import os
import urllib.request
import json
import shutil

parser = argparse.ArgumentParser(description='Install HashiCorp tools')

parser.add_argument('--Program', '-p', choices=['consul', 'Consul', 'vault', 'Vault', 'nomad', 'Nomad'],
    default='consul', dest='program_name',
    help='Which tool to install.  Valid values are consul, vault, nomad.')
parser.add_argument('--Version', '-v', default='latest',help='The version to download and install (default: latest open source version)')
parser.add_argument('--Download-location', '-loc', default='https://releases.hashicorp.com', help='The URL to download from (default: https://releases.hashicorp.com)')
parser.add_argument('--Skip-download', type=bool, default=False, help='Use local archive')
parser.add_argument('--Archive-location', '-al', default='', help='Location of local archive')
parser.add_argument('--Install-dir', '-id', default='/usr/local/bin', help='Where to place the executable.  Default: /usr/local/bin')
parser.add_argument('--Create-users', '-cu', default=True, help='Create user or group')
#parser.add_argument('--no-install-prereqs', default=False, help='Do not install jq, wget, unzip'))
parser.add_argument('--Create-directories', '-cd', default=True, help='Create directories')
parser.add_argument('--Create-unit-files', '-cuf', default=True, help='Create systemd unit files')
parser.add_argument('--Enable-systemd-service', '-ess', default=True, help='Enable systemd service')
parser.add_argument('--Create-config-file', '-ccf',default=False, help="Build config file")

parser.add_argument('--Config-only', '-co', default=False, help="Only create the config file")

# Consul/Nomad options
parser.add_argument('--Is-Server', '-server', type=bool, default=False, help="Install default server config file")
parser.add_argument('--Datacenter', '-dc', default='dc1', help="Which datacenter is the agent in?")
parser.add_argument('--Autojoin', '-aj', help="Autojoin stanza")
parser.add_argument('--Loglevel', '-log', default='INFO', help="Log level for config")

parser.add_argument('--Read-Config-stdin', default=False, help="Read config file piped in")
parser.add_argument('--Read-Config-File', default=False, help="Read config file piped in")
parser.add_argument('--Config-File', help='Location of config file (i.e., /tmp/client.hcl)')

args = parser.parse_args()

program_name = args.program_name.lower()

# should return something like 'consul_1.2.3'
def build_dir_name():
    if args.Version.lower() is 'latest':
        return get_latest_version()
    else:
        return program_name + '_' + args.Version.lower()

# should return something like '1.2.3'
def get_latest_version():
    url = 'https://checkpoint-api.hashicorp.com/v1/check/{}'.format(program_name)
    with urllib.request.urlopen(url) as response:
        text = response.read().decode('utf-8')
        return json.loads(text)['current_version']


# https://releases.hashicorp.com/consul/1.2.3/
def build_download_url(version):
    return '{}/{}/{}'.format(program_name, version, build_file_name(version))

# filename: consul_1.2.3_linux_amd64.zip
def build_file_name(version):
    return '{}_{}_{}_amd64.zip'.format(program_name, version, platform.system().lower())
   
def run_cmd(command):
    subprocess.run(command.split(" "))

def unzip(filename):
    name = ''
    with zipfile.ZipFile(filename) as zfile:
        zfile.extractall(path='/tmp/')
    # python zipfile does not preserve executable permission
    os.chmod('/tmp/{}'.format(program_name), 0o755)

def download_binary(url):
    if (url.startswith('http')):
        urllib.request.urlretrieve(url, '/tmp/{}.zip'.format(program_name))
    elif (url.startswith('s3')):
        retrieve_from_s3(url)
    else:
        print("unsupported url")

def retrieve_from_s3(path):
     print('define me!')

# Including our unit files
consul_unit_file = '''
[Unit]
Description=Consul Agent
Requires=network-online.target
After=network.target

[Service]
User=consul
Group=consul
ExecStart={}/consul agent -config-dir /etc/consul/ $FLAGS
ExecReload=/bin/kill -HUP $MAINPID
KillSignal=SIGTERM
Restart=on-failure
LimitNOFILE=131072

[Install]
WantedBy=multi-user.target
'''.format(args.Install_dir)

vault_unit_file = '''
[Unit]
Description="HashiCorp Vault - A tool for managing secrets"
Documentation=https://www.vaultproject.io/docs/
Requires=network-online.target
After=network-online.target
ConditionFileNotEmpty=/etc/vault/vault.hcl
Wants=consul.service
After=consul.service

[Service]
User=vault
Group=vault
ProtectSystem=full
ProtectHome=read-only
PrivateTmp=yes
PrivateDevices=yes
SecureBits=keep-caps
Capabilities=CAP_IPC_LOCK+ep
CapabilityBoundingSet=CAP_SYSLOG CAP_IPC_LOCK
LimitMEMLOCK=infinity
NoNewPrivileges=yes
ExecStart={}/vault server -config=/etc/vault/vault.hcl
ExecReload=/bin/kill --signal HUP $MAINPID
KillMode=process
KillSignal=SIGINT
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
StartLimitIntervalSec=60
StartLimitBurst=3

[Install]
WantedBy=multi-user.target
'''.format(args.Install_dir)

nomad_unit_file = '''
[Unit]
Description=Nomad
Documentation=https://nomadproject.io/docs/
Wants=network-online.target
After=network-online.target

# If you are running Consul, please uncomment following Wants/After configs.
# Assuming your Consul service unit name is "consul"
Wants=consul.service
After=consul.service

[Service]
KillMode=process
KillSignal=SIGINT
ExecStart={}/nomad agent -config /etc/nomad
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=2
StartLimitBurst=3
StartLimitIntervalSec=10
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
'''.format(args.Install_dir)

# Please note that this is not a fully featured lexer/parser.  You must 
# ensure that you are passing in what will become valid HCL.
def build_hcl_config(conf, value):
    conf += conf + "\n{}".format(value)
    return conf

def build_consul_config():
    conf = 'client_addr = "0.0.0.0"\ndata_dir    = "/opt/consul"'
    conf = build_hcl_config(conf, 'server = {}'.format(str(args.Is_Server).lower()))
    conf = build_hcl_config(conf, 'datacenter = {}'.format(str(args.Datacenter).lower()))
    conf = build_hcl_config(conf, 'retry_join = [{}]'.format(str(args.Autojoin)))
    return conf

def build_nomad_config():
    conf = 'client_addr = "0.0.0.0"\ndata_dir    = "/opt/nomad"'
    build_hcl_config(conf, 'server = {}'.format(str(args.Is_Server).lower()))
    build_hcl_config(conf, 'datacenter = {}'.format(str(args.Datacenter).lower()))
    build_hcl_config(conf, 'retry_join = [{}]'.format(str(args.Autojoin)))
    return conf

def build_vault_config():
    conf = "ui = true\n"
    vault_storage(conf)
    vault_telemetry(conf)
    vault_listener(conf)
    return conf

def vault_storage(conf):
    return

def vault_telemetry(conf):
    return

def vault_listener(conf):
    return

# Reference the function based on program_name 
config_builder = {
    'consul' : build_consul_config,
    'vault'  : build_vault_config,
    'nomad'  : build_nomad_config
}

client_hcl = """
client_addr      = "0.0.0.0"
data_dir         = "/opt/consul"
datacenter       = "east"
log_level        = "INFO"
server           = false
acl_datacenter   = "east"
acl_down_policy  = "extend-cache"
retry_join       = [
    "provider=gce project_name=connect-env tag_value=consul-server"
]
"""


s = '''
echo "Updating and installing required software..."
sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq > /dev/null
sudo DEBIAN_FRONTEND=noninteractive apt-get -qq upgrade > /dev/null
sudo DEBIAN_FRONTEND=noninteractive apt-get install -qq unzip wget jq python3-pip > /dev/null

# Put consul.zip file in /tmp before running the script, or
echo "Installing Consul"
if [ ! -f /tmp/consul.zip ]; then
    echo "Downloading latest Consul binary..."
    cd /tmp && wget `echo "https://releases.hashicorp.com/consul/$(curl -s https://checkpoint-api.hashicorp.com/v1/check/consul | jq -r -M '.current_version')/consul_$(curl -s https://checkpoint-api.hashicorp.com/v1/check/consul | jq -r -M '.current_version')_linux_amd64.zip"` -O consul.zip
fi

cd /tmp && sudo unzip consul.zip -d /usr/local/bin/

echo "Creating consul user and group"
sudo adduser --no-create-home --disabled-password --gecos "" consul

echo "Creating directories"
sudo mkdir -p /etc/consul/
sudo chown -R consul:consul /etc/consul/
sudo mkdir -p /opt/consul/
sudo chown -R consul:consul /opt/consul/


# systemd
echo "creating systemd unit file"
cat <<EOF | sudo tee /lib/systemd/system/consul.service
[Unit]
Description=Consul Agent
Requires=network-online.target
After=network.target

[Service]
User=consul
Group=consul
ExecStart=/usr/local/bin/consul agent -config-dir /etc/consul/ $FLAGS
ExecReload=/bin/kill -HUP $MAINPID
KillSignal=SIGTERM
Restart=on-failure
LimitNOFILE=131072
[Install]
WantedBy=multi-user.target
EOF

sudo chmod 0664 /lib/systemd/system/consul*

# we don't want to enable the service so this is suitable for image building
sudo systemctl daemon-reload
sudo systemctl disable consul.service
'''


create_directories = args.Create_directories
create_user = args.Create_users
retrieve_binary = args.Skip_download == False
create_systemd = args.Create_unit_files
enable_service = args.Enable_systemd_service
build_conf = args.Create_config_file

# start the install
if __name__ == "__main__":
    if args.Config_only is False:
        if create_user:
            print('Creating {} user and group'.format(program_name))
            run_cmd('sudo adduser --no-create-home --disabled-password --gecos "" {}'.format(program_name))

        if create_directories:
            print("Creating directories")
            os.makedirs("/etc/{}/".format(program_name), exist_ok=True)
            shutil.chown("/etc/{}/".format(program_name), user=program_name, group=program_name)
            if program_name is not "vault":
                os.makedirs("/opt/{}/".format(program_name),exist_ok=True)
                shutil.chown("/opt/{}/".format(program_name), user=program_name, group=program_name)


        if retrieve_binary:
            if not args.Archive_location:
                print('Retrieving binary from {}'.format(args.Download_location))
                if args.Version.lower() == 'latest':
                    version = get_latest_version()
                else:        
                    version = args.Version    
                url = '{}/{}'.format(args.Download_location, build_download_url(version))
                
                print('Downloading {}'.format(url))
                download_binary(url)
            else:
                print('Unzipping binary {}'.format(args.Archive_location))
                unzip(args.Archive_location)
            unzip('/tmp/{}.zip'.format(program_name))
            shutil.move('/tmp/{}'.format(program_name), '{}/{}'.format(args.Install_dir, program_name))
            print('{} placed in {}'.format(program_name, args.Install_dir))


        if create_systemd:
            print('Creating systemd unit files...')
            path = '/lib/systemd/system/{}.service'.format(program_name)
            unit_file = open(path, 'w')
            units = {
                'consul': consul_unit_file,
                'vault': vault_unit_file,
                'nomad': nomad_unit_file
            }
            unit_file.write(units[program_name])
            unit_file.close()

        if enable_service:
            commands = [
                "sudo systemctl daemon-reload",
                "sudo systemctl disable {}.service".format(program_name)
            ]

        if build_conf:
            print("Building {} config file".format(program_name))
            config_builder[program_name]()

    if args.Config_only or args.Create_config_file:
        print(config_builder[program_name]())

