# NATS Server Deployment

Three options for the specific infrastructure (k8s cluster + homelab hosts).

## Option A: k8s Pod (Preferred)

Cluster has at least one node (kates, nuclhed, nucular). NATS is lightweight (~20MB).

```yaml
# nats-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nats
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: nats
  template:
    metadata:
      labels:
        app: nats
    spec:
      containers:
      - name: nats
        image: nats:latest
        args: ["-js", "-m", "8222"]
        ports:
        - containerPort: 4222   # client connections
        - containerPort: 8222   # HTTP monitoring
---
apiVersion: v1
kind: Service
metadata:
  name: nats
  namespace: default
spec:
  selector:
    app: nats
  ports:
  - name: client
    port: 4222
    targetPort: 4222
  - name: monitor
    port: 8222
    targetPort: 8222
```

Apply: `kubectl apply -f nats-deployment.yaml`

Agents connect to `nats://nats:4222` from within the cluster. If agents run on host machines (not k8s), expose with NodePort:

```yaml
spec:
  type: NodePort
  ports:
  - name: client
    port: 4222
    targetPort: 4222
    nodePort: 34222
```

Then agents connect to `nats://<any-node-ip>:34222`.

## Option B: Docker on One Host

Simplest option for testing. Run on any host with Docker:

```bash
docker run -d --name nats \
  --restart unless-stopped \
  -p 4222:4222 -p 8222:8222 \
  nats:latest -js -m 8222
```

Connect at `nats://<host-ip>:4222`.

To persist JetStream data:

```bash
docker run -d --name nats \
  --restart unless-stopped \
  -p 4222:4222 -p 8222:8222 \
  -v nats-data:/data \
  nats:latest -js -m 8222 --store_dir /data
```

## Option C: systemd on Diffuser or Mink

Direct binary install for the lowest overhead:

```bash
# Download
curl -sfL https://github.com/nats-io/nats-server/releases/latest/download/nats-server-linux-amd64.tar.gz \
  | tar xz
sudo mv nats-server /usr/local/bin/

# Create user
sudo useradd -r nats -s /sbin/nologin

# systemd unit
sudo tee /etc/systemd/system/nats-server.service > /dev/null <<'SERVICEEOF'
[Unit]
Description=NATS Server
Documentation=https://docs.nats.io/
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/nats-server -js -m 8222
Restart=always
RestartSec=5
User=nats
Group=nats
LimitNOFILE=100000

[Install]
WantedBy=multi-user.target
SERVICEEOF

sudo mkdir -p /var/lib/nats-server
sudo chown nats:nats /var/lib/nats-server
sudo systemctl daemon-reload
sudo systemctl enable --now nats-server

# Verify
sudo systemctl status nats-server
```

## Verification

```bash
# From any agent host
curl http://<nats-host>:8222/
# Should return NATS server info JSON

# Install nats CLI for interactive testing
go install github.com/nats-io/natscli/nats@latest
# or download from releases

# Pub/sub test
nats pub test.hello "hello world"
nats sub test.hello
```

## Common Issues

- **Port already in use.** Check with `ss -tlnp | grep 4222`. Pick another port if conflict.
- **Firewall blocking.** `ufw allow 4222/tcp` if using ufw. Or use NodePort with an allowed port.
- **DNS resolution.** If agents on host machines use k8s service DNS, ensure CoreDNS is reachable from the host. Easier: use NodePort + IP address or Option C (systemd on same host as one agent).
