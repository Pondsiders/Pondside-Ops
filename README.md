# Pondside-Ops

Version-controlled infrastructure for Pondside's VMs — cloud-init, libvirt
domain definitions, systemd units, and service configs for every virtual
machine we run on Primer (or anywhere else in the tailnet that isn't Primer
itself).

## What lives here

One directory per VM. Each directory is self-contained:

```
ember/               GPU inference compute node (3080 Ti, llama-swap + llama.cpp)
  domain.xml           libvirt domain definition — hardware shape, GPU passthrough
  cloud-init/          first-boot automation
  llama-swap/          service config, version-controlled
  motd                 login message with manual-setup steps
  BUILD_LOG.md         deployment diary, decisions and deviations
```

Future VMs (alpha, rosemary, others) get their own sibling directories when we
build them.

## What does NOT live here

- Alpha-App, Rosemary-App, Alpha-SDK, Rosemary-SDK (those are application code,
  in their own repos under Workshop/Projects)
- Anything Primer itself runs bare-metal (ZFS pools, Docker stacks, Abe's
  substrate work) — that's Abe's territory
- Secrets (no auth keys, no passwords, no tokens — `.env` files are gitignored)

## Relationship to Alpha-Ops

Alpha-Ops was the original "how we build VMs" scratch space, scoped narrowly
around building the Alpha VM that never ended up shipping. Pondside-Ops is the
generalized successor. Alpha-Ops is NOT being migrated — its CONVENTIONS.md
carried forward, its cloud-init templates are reference material. Pondside-Ops
starts fresh.

## Workflow

1. Design a VM in this repo (cloud-init, domain.xml, service configs).
2. Hand specs to Abe for the actual VM creation on Primer.
3. Capture whatever Abe produced back into this repo (`virsh dumpxml` → commit).
4. Dogfood-test: destroy the VM, redeploy from what's in this repo, verify.
5. That VM is now reproducible from git.

## Principles

- **Cloud-init is minimal.** Install prerequisites and clone source. Humans
  finish the setup on first login using the MOTD as a checklist.
- **Configs fetched from this repo at deploy time.** Raw GitHub URLs. No
  inlining configs into cloud-init.
- **Version pins are explicit.** llama-swap version, llama.cpp commit, nvidia
  driver major — all pinned, upgraded intentionally.
- **One VM per directory.** Shared machinery (scripts, conventions) lives at
  the root, not duplicated per VM.
