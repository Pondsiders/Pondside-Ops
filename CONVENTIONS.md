# Conventions

Carried forward from Alpha-Ops and adjusted for the generalized Pondside-Ops
scope. Read once, reread when adding a new VM.

## Directory layout

```
<vm-name>/
├── BUILD_LOG.md         append-only deploy-and-decision diary
├── domain.xml           libvirt domain definition (virsh dumpxml output)
├── cloud-init/
│   ├── user-data.yaml   first-boot automation
│   └── meta-data.yaml   minimal (hostname, instance-id)
├── <service>/           one dir per long-lived service
│   └── config.yaml        service config, fetched at deploy time
└── motd                 login-time instructions for the human
```

## Cloud-init philosophy

- **Install prerequisites. Clone source. Write MOTD. Stop.**
- Do NOT: `tailscale up`, `cmake build`, `systemctl enable`, run servers.
  Those are manual first-login steps, explicit in the MOTD.
- DO: pin package versions, set environment variables globally, reboot after
  driver installs.
- User accounts: inherit the cloud image default (`ubuntu` on Ubuntu). Jeffery's
  reasoning: `ubuntu@hostname` is a visual cue that you're on a VM and not a
  real machine — reduces risk of rebooting the wrong thing (memory #17092).
- SSH authorized_keys: `alpha@alphafornow.com` and `jefferyharrell@gmail.com`
  baseline on every VM. Add others as the VM's role requires.

## Version pinning

Every external dependency pinned with a specific version or commit:

- **nvidia driver**: major version pinned (e.g. `nvidia-headless-590-open`).
  Minor bumps flow automatically through `apt upgrade`; major version changes
  are intentional (require re-evaluation and rebuild of llama.cpp against new
  CUDA toolkit).
- **llama.cpp**: pinned to a specific commit in `user-data.yaml` (git checkout
  after clone). Updates are intentional and logged in BUILD_LOG.
- **llama-swap**: pinned to a specific release version. Downloaded from
  GitHub releases by exact tag.
- **uv**, **hf_transfer**: installed standalone (not from apt), pinned if the
  repo cadence causes breakage.

## Config fetching

Service configs (e.g. `llama-swap/config.yaml`) live in this repo and are
fetched by the human during first-login setup, not baked into cloud-init.
Pattern:

```bash
sudo curl -fsSL \
  https://raw.githubusercontent.com/Pondsiders/Pondside-Ops/main/<vm>/<service>/config.yaml \
  -o /etc/<service>/config.yaml
```

Rationale: configs change more often than cloud-init. Keeping them in git
means changes propagate via a git pull + `systemctl restart`, not a VM rebuild.

## MOTD shape

The MOTD is a numbered checklist. Every command is copy-pasteable, in order.
Assume the human just logged in as `ubuntu@<vm>` and knows nothing else.

## Secrets

No secrets in this repo. Ever. Public repo.

If a VM needs secrets:
- Tailscale auth keys: generated fresh per deploy, passed via a transient
  mechanism, NOT stored in `user-data.yaml`. Manual `tailscale up` pattern
  handles this.
- Application secrets: `.env` files in the application's own repo, injected
  at container-start time, never in Pondside-Ops.

## BUILD_LOG.md

Append-only. Each deploy gets a dated entry. What changed, what broke, what
we had to work around. This is the diary equivalent for a VM.

Format:

```markdown
## YYYY-MM-DD — short description

What happened. What decisions we made. What to do differently next time.
```

## Destroy/redeploy

The gold-standard for "this VM is reproducible" is: destroy it completely,
redeploy only from what's in this repo + Abe's VM-creation hand, verify the
service comes back up identically. Do this at least once per VM shortly after
first build. Log the result in BUILD_LOG.md.

## Handoff to Abe

The VM creation itself (libvirt commands, zvol creation, virtiofs mount
definitions) is Abe's territory. This repo describes the VM; Abe makes it.

Pattern:
1. Draft cloud-init, MOTD, service configs in this repo.
2. Hand Abe: spec sheet (vCPU, RAM, disks, mounts, GPU passthrough).
3. Abe builds the VM, returns `virsh dumpxml <name>` output.
4. Commit the dumped XML to `<vm>/domain.xml`.
5. Dogfood redeploy; log result.
