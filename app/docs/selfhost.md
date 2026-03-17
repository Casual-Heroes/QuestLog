# Matrix Server Setup Guide
**Self-Hosting Matrix Full Guide - Grab Some Popcorn**

---

## Important Disclaimer

**This guide does NOT cover:**
- Setting up DNS providers (Cloudflare, etc.)
- Configuring firewalls (OPNsense, pfSense, iptables basics)
- Port forwarding
- Basic server administration

**This guide assumes you already know:**
- How DNS works and how to add records
- How to configure your firewall
- Basic networking concepts
- How to SSH into a server

If you don't know this stuff yet, go learn it first. there's tons of guides out there for DNS setup, firewall basics, etc. this guide is strictly focused on getting Matrix running and assumes you've got the networking fundamentals down.

---

## What This Is

Ok so you wanna run your own Matrix server. cool. this guide's got everything you need to get a full production setup running - Synapse, auth, voice/video, Discord bridge, all of it.

When we're done you'll have:

- Synapse homeserver
- MAS authentication (way better than the old OIDC stuff)
- CoTURN for voice/video
- Element Web (your own client)
- Discord bridge
- Federation (connect to other Matrix servers)
- SSL locked down


- **Time:** 3-4 hours
- **Difficulty:** need to know Linux basics
- **Cost:** $10-20/month for VPS or free if selfhosting

---

## What You Need

### Hardware

**bare minimum:**
- 4GB RAM
- 2 CPU cores
- 20GB disk
- public IP

**what you actually want:**
- 8GB RAM (Synapse gets hungry)
- 4 CPU cores
- 50GB disk (media files add up FAST)
- dedicated box or VPS

### Software

- Debian 12 or Ubuntu 22.04 (guide uses Debian 12)
- Your own domain
- Access to DNS records
- Firewall (OPNsense, pfSense, or iptables)

### Skills

You need to know:

- Basic Linux command line
- How to SSH
- What DNS is
- Nginx basics (or be ready to learn)
- Docker basics

If you don't know this stuff, take some extra time to it learn it first. Seriously, it will help!

---

## How It All Fits Together

### Domains

Here's how I set mine up (Swap in your domain):

```
casual-heroes.com
├── matrix.casual-heroes.com     → Synapse
├── sso.casual-heroes.com        → MAS auth
├── gameon.casual-heroes.com     → CoTURN (voice/video)
└── chat.casual-heroes.com       → Element Web
```

### The Stack

```
Users (Element, mobile apps, whatever)
         ↓ HTTPS
    Nginx reverse proxy
    ├── matrix.* → Synapse (8008)
    ├── sso.* → MAS (8080)
    └── chat.* → Element Web

Docker containers:
    ├── Synapse
    ├── PostgreSQL (Synapse DB)
    ├── MAS
    ├── PostgreSQL (MAS DB)
    └── Redis (caching)

System service:
    └── CoTURN (voice/video)
```

---

## Part 1: Server Prep

Get your server ready. don't skip this.

### Update Everything

```bash
sudo apt update && sudo apt upgrade -y
```

### Install Packages

```bash
sudo apt install -y \
    curl \
    wget \
    git \
    nano \
    docker.io \
    docker-compose \
    nginx \
    certbot \
    python3-certbot-nginx \
    coturn \
    sqlite3 \
    iptables \
    iptables-persistent
```

### Firewall Setup

> **WARNING:** mess this up and you lock yourself out of SSH. be careful. If you're using OPNsense or pfSense, set these up in the GUI instead.

```bash
# defaults
sudo iptables -P INPUT DROP
sudo iptables -P FORWARD DROP
sudo iptables -P OUTPUT ACCEPT

# loopback
sudo iptables -A INPUT -i lo -j ACCEPT

# established connections
sudo iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# SSH - DO NOT FORGET THIS
sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT

# HTTP/HTTPS
sudo iptables -A INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 443 -j ACCEPT

# Matrix federation
sudo iptables -A INPUT -p tcp --dport 8448 -j ACCEPT

# TURN (voice/video)
sudo iptables -A INPUT -p tcp --dport 3478 -j ACCEPT
sudo iptables -A INPUT -p udp --dport 3478 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 5349 -j ACCEPT
sudo iptables -A INPUT -p udp --dport 49152:65535 -j ACCEPT

# save it
sudo netfilter-persistent save
```

### DNS

Go to your DNS provider and add these A records:

| Type | Name | Points To |
|------|------|-----------|
| A | matrix | YOUR_SERVER_IP |
| A | sso | YOUR_SERVER_IP |
| A | gameon | YOUR_SERVER_IP |
| A | chat | YOUR_SERVER_IP |

Wait a couple minutes for DNS to propagate, then check:

```bash
dig +short matrix.yourdomain.com
dig +short sso.yourdomain.com
```

Should show your server IP.

### Docker

```bash
# start Docker
sudo systemctl start docker
sudo systemctl enable docker

# add yourself to docker group
sudo usermod -aG docker $USER

# log out and back in
exit
```

SSH back in, then verify:

```bash
sudo docker ps
```

Should show empty list, not permission errors.

---

## Part 2: Synapse Install

Now we're getting to the actual Matrix server.

### Setup Directories

```bash
sudo mkdir -p /opt/synapse
cd /opt/synapse
```

### Generate Config

```bash
sudo docker run -it --rm \
    -v /opt/synapse:/data \
    matrixdotorg/synapse:latest \
    generate
```

It'll ask for your domain - use yours (like casual-heroes.com).

### docker-compose.yml

```bash
sudo nano docker-compose.yml
```

```yaml
version: '3'

services:
  synapse:
    image: matrixdotorg/synapse:latest
    container_name: synapse
    restart: unless-stopped
    ports:
      - "8008:8008"
    volumes:
      - ./data:/data
    environment:
      - SYNAPSE_CONFIG_PATH=/data/homeserver.yaml
    depends_on:
      - synapse-postgres
      - redis
    networks:
      - synapse_default

  synapse-postgres:
    image: postgres:15-alpine
    container_name: synapse-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: synapse
      POSTGRES_PASSWORD: CHANGE_THIS_NOW
      POSTGRES_DB: synapse
    volumes:
      - ./postgres-data:/var/lib/postgresql/data
    networks:
      - synapse_default

  redis:
    image: redis:alpine
    container_name: synapse-redis
    restart: unless-stopped
    networks:
      - synapse_default

networks:
  synapse_default:
    driver: bridge
```

> **Change that postgres password before you run anything.**

### homeserver.yaml

```bash
sudo nano /opt/synapse/homeserver.yaml
```

Find and change these sections:

```yaml
server_name: "casual-heroes.com"  # your domain
public_baseurl: "https://matrix.casual-heroes.com"

# database - use postgres not sqlite
database:
  name: psycopg2
  args:
    user: synapse
    password: SAME_PASSWORD_FROM_DOCKER_COMPOSE
    database: synapse
    host: synapse-postgres
    cp_min: 5
    cp_max: 10

# listeners
listeners:
  - port: 8008
    tls: false
    type: http
    x_forwarded: true
    bind_addresses: ['0.0.0.0']
    resources:
      - names: [client, federation]
        compress: false

# registration - turn this OFF after you make your account
enable_registration: true
enable_registration_without_verification: true

# media
media_store_path: "/data/media_store"
max_upload_size: 50M

# media retention - auto cleanup
media_retention:
  local_media_lifetime: 2y
  remote_media_lifetime: 1y

forgotten_room_retention_period: 7d

# URL previews
# NOTE: This can leak your server's metadata. Keep false if privacy matters.
url_preview_enabled: false

# REQUIRED if url_preview_enabled is true - prevents SSRF attacks
url_preview_ip_range_blacklist:
  - '127.0.0.0/8'
  - '10.0.0.0/8'
  - '172.16.0.0/12'
  - '192.168.0.0/16'
  - '100.64.0.0/10'
  - '169.254.0.0/16'
  - '192.0.0.0/24'
  - '192.0.2.0/24'
  - '198.51.100.0/24'
  - '203.0.113.0/24'
  - '192.88.99.0/24'
  - '198.18.0.0/15'
  - '224.0.0.0/4'
  - '240.0.0.0/4'
  - '::1/128'
  - 'fe80::/10'
  - 'fc00::/7'
  - 'ff00::/8'
  - '2001:db8::/32'
  - 'fec0::/10'

max_spider_size: 10M

# redis caching
caches:
  global_factor: 2.0

redis:
  enabled: true
  host: redis
  port: 6379
```

> **That URL blacklist is NOT optional.** Without it someone can post a link like `http://127.0.0.1:8008/_synapse/admin` and your server will try to fetch it. That's a Server-Side Request Forgery (SSRF) vulnerability.

### Start Synapse

```bash
cd /opt/synapse
sudo docker-compose up -d
```

Check logs:

```bash
sudo docker logs synapse -f
```

Press Ctrl+C to exit logs.

### Create Admin Account

```bash
sudo docker exec -it synapse register_new_matrix_user \
    http://localhost:8008 \
    -c /data/homeserver.yaml \
    -u YOUR_USERNAME \
    -p YOUR_PASSWORD \
    -a
```

The `-a` flag makes you admin.

### Turn Off Registration

> **Do this NOW or random people will register on your server.**

```bash
sudo nano /opt/synapse/homeserver.yaml
```

Change to:

```yaml
enable_registration: false
```

Then restart:

```bash
sudo docker-compose restart synapse
```

---

## Part 3: Nginx and SSL

### Get SSL Certs

```bash
sudo certbot certonly --nginx -d matrix.casual-heroes.com
sudo certbot certonly --nginx -d sso.casual-heroes.com
sudo certbot certonly --nginx -d gameon.casual-heroes.com
sudo certbot certonly --nginx -d chat.casual-heroes.com
```

### Nginx Config

```bash
sudo nano /etc/nginx/sites-available/matrix
```

```nginx
# Matrix server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    listen 8448 ssl http2 default_server;
    listen [::]:8448 ssl http2 default_server;

    server_name matrix.casual-heroes.com;

    ssl_certificate /etc/letsencrypt/live/matrix.casual-heroes.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/matrix.casual-heroes.com/privkey.pem;

    location ~ ^(/_matrix|/_synapse/client) {
        proxy_pass http://localhost:8008;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Host $host;
        client_max_body_size 50M;
    }
}

# HTTP redirect
server {
    listen 80;
    listen [::]:80;
    server_name matrix.casual-heroes.com;
    return 301 https://$host$request_uri;
}
```

Enable it:

```bash
sudo ln -s /etc/nginx/sites-available/matrix /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Test It

```bash
curl https://matrix.casual-heroes.com/_matrix/client/versions
```

Should return JSON with version info.

---

## Part 4: Federation

### What Is Federation

Think email - you can email from Gmail to someone on Outlook. Matrix is the same. Your server can talk to other Matrix servers. Users on different servers can chat, join rooms, all that.

### Why Use It

**good stuff:**
- talk to anyone on any Matrix server
- if one server dies, rooms stay alive on others
- no single company owns everything
- join public rooms on matrix.org

**not so good:**
- room content gets copied to every federated server
- can't fully control users from other servers
- your server stores history from federated rooms
- legal risk (you're storing other people's content)

### Option 1: Open Federation (default)

Just don't set `federation_domain_whitelist` and you're federating with everyone.

**pros:** maximum reach, anyone can join
**cons:** anyone CAN join, spam risk

### Option 2: Whitelist (recommended for private servers)

```bash
sudo nano /opt/synapse/homeserver.yaml
```

```yaml
federation_domain_whitelist:
  - casual-heroes.com    # YOUR DOMAIN - REQUIRED
  - matrix.org           # if you want to join public rooms
```

> **You MUST include your own domain** or room publishing breaks.

Restart after changes:

```bash
sudo docker-compose restart synapse
```

### Option 3: No Federation

```yaml
federation_domain_whitelist: []
```

Completely isolated. Max privacy, but can't talk to other servers.

### Test Federation

Go to [federationtester.matrix.org](https://federationtester.matrix.org) and enter your domain. All green checks = working.

### Media Retention

When federated users send images, your server caches them. This adds up fast.

```yaml
media_retention:
  local_media_lifetime: 2y    # your uploads
  remote_media_lifetime: 1y   # federated cache
```

This deletes media based on **last access**, not upload date - so frequently-used media stays warm while old stuff gets cleaned up.

Check current usage:

```bash
du -sh /opt/synapse/media_store
du -sh /opt/synapse/media_store/remote_content
```

---

## Part 5: MAS Authentication

MAS is the new auth system for Matrix. It replaces the old OIDC setup and gives you QR code login, better security, and a proper account management UI.

### Setup MAS

```bash
sudo mkdir -p /opt/mas
cd /opt/mas
```

### docker-compose.yml

```yaml
version: '3'

services:
  mas:
    image: ghcr.io/element-hq/matrix-authentication-service:latest
    container_name: mas
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - ./config.yaml:/config/config.yaml:ro
      - ./data:/data
    depends_on:
      - mas-postgres
    networks:
      - mas_default

  mas-postgres:
    image: postgres:15-alpine
    container_name: mas-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: mas
      POSTGRES_PASSWORD: CHANGE_THIS_PASSWORD
      POSTGRES_DB: mas
    volumes:
      - ./postgres-data:/var/lib/postgresql/data
    networks:
      - mas_default

networks:
  mas_default:
    driver: bridge
```

### MAS Config

```yaml
http:
  public_base: https://sso.casual-heroes.com
  listeners:
    - name: web
      binds:
        - host: 0.0.0.0
          port: 8080
      resources:
        - name: discovery
        - name: human
        - name: oauth
        - name: compat
        - name: graphql
          playground: true

database:
  uri: postgresql://mas:YOUR_PASSWORD@mas-postgres/mas

matrix:
  homeserver: casual-heroes.com
  endpoint: https://matrix.casual-heroes.com
  secret: GENERATE_RANDOM_SECRET_HERE

clients:
  - client_id: 01HQDS4V91H4T9EZ2PWYBW1FZA
    client_auth_method: client_secret_basic
    client_secret: GENERATE_ANOTHER_SECRET

passwords:
  enabled: true
  schemes:
    - version: 1
      algorithm: argon2id

policy:
  wasm_module: /usr/local/share/mas-cli/policy.wasm

templates:
  path: /usr/local/share/mas-cli/templates
  assets_manifest: /usr/local/share/mas-cli/manifest.json

# Email (optional but recommended for password reset)
email:
  from: "noreply@casual-heroes.com"
  reply_to: "support@casual-heroes.com"
  transport: smtp
  hostname: your-smtp-server.com
  port: 587
  mode: starttls
  username: your-email@casual-heroes.com
  password: your-email-password
```

Generate your secrets:

```bash
openssl rand -hex 32    # use for matrix.secret
openssl rand -hex 32    # use for client_secret
```

### Update Synapse for MAS

```bash
sudo nano /opt/synapse/homeserver.yaml
```

Add at the bottom:

```yaml
experimental_features:
  msc3861:
    enabled: true
    issuer: https://sso.casual-heroes.com/
    client_id: 01HQDS4V91H4T9EZ2PWYBW1FZA
    client_auth_method: client_secret_basic
    client_secret: SAME_SECRET_FROM_MAS_CONFIG
    admin_token: GENERATE_NEW_RANDOM_TOKEN
    account_management_url: https://sso.casual-heroes.com/account
```

Restart Synapse:

```bash
cd /opt/synapse
sudo docker-compose restart
```

### Start MAS

```bash
cd /opt/mas
sudo docker-compose up -d
```

### Nginx for MAS

```nginx
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;

    server_name sso.casual-heroes.com;

    ssl_certificate /etc/letsencrypt/live/sso.casual-heroes.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/sso.casual-heroes.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 80;
    server_name sso.casual-heroes.com;
    return 301 https://$host$request_uri;
}
```

### Test MAS

Visit `https://sso.casual-heroes.com` - should show the MAS login page.

---

## Part 6: CoTURN (Voice and Video)

CoTURN relays voice and video call traffic. Without it, calls may fail depending on NAT/firewall configurations.

### Configure CoTURN

```bash
sudo nano /etc/turnserver.conf
```

```conf
# listening
listening-port=3478
tls-listening-port=5349

# relay
min-port=49152
max-port=65535

# authentication
use-auth-secret
static-auth-secret=GENERATE_RANDOM_SECRET
realm=casual-heroes.com

# SSL
cert=/etc/letsencrypt/live/gameon.casual-heroes.com/fullchain.pem
pkey=/etc/letsencrypt/live/gameon.casual-heroes.com/privkey.pem

# performance
total-quota=100
bps-capacity=0
stale-nonce=600

# logging
verbose
log-file=/var/log/turnserver.log
```

Generate secret:

```bash
openssl rand -hex 32
```

### Update Synapse for TURN

```yaml
turn_uris:
  - "turn:gameon.casual-heroes.com:3478?transport=udp"
  - "turn:gameon.casual-heroes.com:3478?transport=tcp"
  - "turns:gameon.casual-heroes.com:5349?transport=udp"
  - "turns:gameon.casual-heroes.com:5349?transport=tcp"

turn_shared_secret: "SAME_SECRET_FROM_TURNSERVER_CONF"
turn_user_lifetime: 86400000
turn_allow_guests: false
```

```bash
sudo docker-compose restart synapse
```

### Start CoTURN

```bash
sudo systemctl start coturn
sudo systemctl enable coturn
sudo systemctl status coturn
```

### Test TURN

Go to [webrtc.github.io/samples/src/content/peerconnection/trickle-ice](https://webrtc.github.io/samples/src/content/peerconnection/trickle-ice/) and enter your TURN server details. You should see relay candidates.

---

## Part 7: Backup and Maintenance

### Critical Files

> **Back these up. You CANNOT recover without them.**

```
/opt/synapse/homeserver.signing.key   ← MOST CRITICAL
/opt/synapse/homeserver.yaml
/opt/mas/config.yaml
/etc/letsencrypt/
/etc/turnserver.conf
```

### Database Backups

```bash
# Backup Synapse database
sudo docker exec synapse-postgres pg_dump -U synapse synapse > synapse_backup_$(date +%Y%m%d).sql

# Backup MAS database
sudo docker exec mas-postgres pg_dump -U mas mas > mas_backup_$(date +%Y%m%d).sql
```

### Automated Backup Script

```bash
sudo nano /opt/backup-matrix.sh
```

```bash
#!/bin/bash
BACKUP_DIR="/opt/backups/matrix"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

docker exec synapse-postgres pg_dump -U synapse synapse > $BACKUP_DIR/synapse_$DATE.sql
docker exec mas-postgres pg_dump -U mas mas > $BACKUP_DIR/mas_$DATE.sql

cp /opt/synapse/homeserver.signing.key $BACKUP_DIR/signing_key_$DATE
cp /opt/synapse/homeserver.yaml $BACKUP_DIR/synapse_config_$DATE.yaml
cp /opt/mas/config.yaml $BACKUP_DIR/mas_config_$DATE.yaml

# Keep only last 7 days
find $BACKUP_DIR -name "*.sql" -mtime +7 -delete
find $BACKUP_DIR -name "*config*" -mtime +7 -delete

echo "Backup completed: $DATE"
```

```bash
sudo chmod +x /opt/backup-matrix.sh
```

Add to cron (runs daily at 2 AM):

```bash
sudo crontab -e
# Add: 0 2 * * * /opt/backup-matrix.sh
```

### Restore from Backup

```bash
# Stop services
cd /opt/synapse && sudo docker-compose down
cd /opt/mas && sudo docker-compose down

# Restore databases
cat synapse_backup_20250301.sql | sudo docker exec -i synapse-postgres psql -U synapse synapse
cat mas_backup_20250301.sql | sudo docker exec -i mas-postgres psql -U mas mas

# Restore configs
sudo cp synapse_config_backup.yaml /opt/synapse/homeserver.yaml
sudo cp signing_key_backup /opt/synapse/homeserver.signing.key
sudo cp mas_config_backup.yaml /opt/mas/config.yaml

# Start services
cd /opt/synapse && sudo docker-compose up -d
cd /opt/mas && sudo docker-compose up -d
```

---

## Part 8: Upgrading

### Always backup before upgrading.

### Upgrade Synapse

```bash
cd /opt/synapse

# Backup first
sudo docker exec synapse-postgres pg_dump -U synapse synapse > pre_upgrade_backup.sql

# Pull and restart
sudo docker-compose pull synapse
sudo docker-compose down
sudo docker-compose up -d

# Watch logs
sudo docker logs synapse -f
```

### Upgrade MAS

```bash
cd /opt/mas
sudo docker exec mas-postgres pg_dump -U mas mas > pre_upgrade_mas.sql
sudo docker-compose pull
sudo docker-compose down
sudo docker-compose up -d
sudo docker logs mas -f
```

### Upgrade CoTURN

```bash
sudo apt update
sudo apt upgrade coturn
sudo systemctl restart coturn
```

### SSL Certificate Auto-Renewal

```bash
# Test renewal
sudo certbot renew --dry-run

# Check timer is active
sudo systemctl status certbot.timer

# Enable if not active
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

---

## Part 9: Performance Notes

### Single-Process vs Workers

**This guide uses single-process Synapse.** For most small/medium servers (under 100 active users), this is fine.

**Consider workers when you hit:**
- 100+ active users
- Heavy federation traffic
- CPU/RAM consistently maxing out

See the [official workers docs](https://matrix-org.github.io/synapse/latest/workers.html) when you get there.

### Quick Performance Fixes

**Check Redis is connected:**

```bash
sudo docker logs synapse | grep -i redis
# Should see "Connected to Redis"
```

**Increase cache factor:**

```yaml
caches:
  global_factor: 3.0
```

**Check database size:**

```bash
sudo docker exec synapse-postgres psql -U synapse -c \
  "SELECT datname, pg_size_pretty(pg_database_size(datname)) FROM pg_database;"
```

---

## Part 10: Troubleshooting

### Synapse Won't Start

```bash
sudo docker logs synapse --tail 100
```

Common causes: database connection failed, port 8008 in use, invalid config syntax.

**Database connection failed:**
```bash
sudo docker ps | grep postgres
sudo docker exec -it synapse-postgres psql -U synapse -d synapse
```

### MAS Won't Start

```bash
sudo docker logs mas --tail 100
sudo docker exec mas mas-cli config check
```

### Federation Not Working

```bash
curl https://matrix.yourdomain.com:8448/_matrix/federation/v1/version
```

Should return JSON. If it errors: check port 8448 firewall, SSL cert, nginx config, and make sure your own domain is in the whitelist.

### Voice/Video Calls Failing

```bash
sudo systemctl status coturn
sudo tail -f /var/log/turnserver.log
```

Common causes: UDP ports 49152-65535 blocked, TURN SSL cert expired, wrong shared secret in Synapse config.

### High Storage Usage

```bash
du -sh /opt/synapse/media_store
du -sh /opt/synapse/postgres-data
```

**Force media cache purge:**
```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  "http://localhost:8008/_synapse/admin/v1/purge_media_cache?before_ts=$(date -d '180 days ago' +%s)000"
```

### Can't Login After MAS Setup

Old sessions don't work with MAS. Users need to fully log out and log back in through the new OIDC flow.

---

## Maintenance Checklist

### Weekly
```bash
df -h
sudo docker ps
sudo systemctl status coturn
```

### Monthly
```bash
cd /opt/synapse && sudo docker-compose pull
cd /opt/mas && sudo docker-compose pull
sudo docker logs synapse --tail 100 | grep -i error
sudo docker logs mas --tail 100 | grep -i error
```

### Quarterly
```bash
sudo apt update && sudo apt upgrade
ls -lh /opt/backups/matrix/
sudo certbot renew --dry-run
```

---

## Appendix

### Resources
- [Matrix Homeserver Overview](https://matrix.org/homeserver/about/)
- [Matrix for Instant Messaging](https://matrix.org/docs/chat_basics/matrix-for-im/)
- [Matrix Specification](https://spec.matrix.org/latest/)
- [Matrix Clients](https://matrix.org/ecosystem/clients/)
- [Matrix Bridges](https://matrix.org/ecosystem/bridges/) (Will cover in another guide/video)
- [Synapse Welcome & Overview](https://matrix-org.github.io/synapse/latest/welcome_and_overview.html)

---

That's it. You now have a complete, production-ready Matrix server with Synapse, MAS auth, CoTURN for voice/video, automated backups, and everything locked down.

Questions? Drop into [QuestChat](https://chat.casual-heroes.com) and ask in `#just-hanging:casual-heroes.com`.
