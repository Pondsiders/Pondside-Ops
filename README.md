# Pondside-Ops

Version-controlled infrastructure for the things we run — VMs on Primer,
containers (here or on a dedicated Docker-runner VM), serverless on Modal,
and whatever comes next. Cloud-init, libvirt domain definitions, systemd
units, service configs, Modal Functions — the operational stuff that isn't
application code.

## What lives here

One directory per deployable unit — a VM, a container stack, a Modal app.
Each directory is self-contained:

```
ember/               GPU inference compute node (3080 Ti, llama-swap + llama.cpp)
  domain.xml           libvirt domain definition — hardware shape, GPU passthrough
  cloud-init/          first-boot automation
  llama-swap/          service config, version-controlled
  motd                 login message with manual-setup steps
  BUILD_LOG.md         deployment diary, decisions and deviations
```

Future deployable units (VMs, container stacks, Modal apps) get their own
sibling directories when we build them. Sibling examples we can see coming:
`modal-serverless-inference/` (Qwen + Gemma fallbacks), `modal-training/`
(fine-tuning runs), `harbormaster/` (LiteLLM container), maybe a
`docker-runner/` VM that hosts everything container-shaped.

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

## Workflow (VMs)

1. Design a VM in this repo (cloud-init, domain.xml, service configs).
2. Hand specs to Abe for the actual VM creation on Primer.
3. Capture whatever Abe produced back into this repo (`virsh dumpxml` → commit).
4. Dogfood-test: destroy the VM, redeploy from what's in this repo, verify.
5. That VM is now reproducible from git.

## Workflow (Modal, containers, other)

Simpler. Each non-VM deployable has its own README inside its directory
describing how to stand it up (`modal deploy foo.py`, `docker compose up -d`,
etc.). Same BUILD_LOG.md pattern applies: append-only diary of deploys,
decisions, and deviations.

## Principles

- **Cloud-init is minimal.** Install prerequisites and clone source. Humans
  finish the setup on first login using the MOTD as a checklist.
- **Configs fetched from this repo at deploy time.** Raw GitHub URLs. No
  inlining configs into cloud-init.
- **Version pins are explicit.** llama-swap version, llama.cpp commit, nvidia
  driver major — all pinned, upgraded intentionally.
- **One deployable unit per directory.** Shared machinery (scripts,
  conventions) lives at the root, not duplicated per unit.
