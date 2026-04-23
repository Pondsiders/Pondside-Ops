# Ember Build Log

Append-only deployment diary for the GPU inference VM on Primer.

## Spec

- **Role**: OpenAI-compatible inference endpoint for Alpha (Qwen 3.5 4B + Qwen 3 Embedding 4B) and Rosemary (Gemma 3 12B + nomic-embed-text-v1.5).
- **Host**: Primer (bare-metal Ubuntu, KVM/libvirt).
- **GPU**: NVIDIA RTX 3080 Ti (GA102, 12 GB VRAM), passed through via VFIO.
- **Base image**: Ubuntu 24.04 LTS cloud image.
- **Networking**: Tailscale node, hostname `ember`, FQDN `ember.tail8bd569.ts.net`.
- **Storage**: system disk on zvol `tank/vms/ember/disk0`. Models in virtiofs-shared `tank/models` mounted at `/mnt/models` (recordsize=1M).
- **Build-time spec**: 20 vCPU, 80 GB RAM. Steady-state spec after compile: 6 vCPU, 12 GB RAM.

## 2026-04-21 — Original prototype deploy

Built by Abe from first principles with a minimal cloud-init (see memory
#17091 and #17096). Issues and their resolutions:

- `nvidia-headless-590-open` does NOT pull `nvidia-utils-590`. Had to add
  explicitly for `nvidia-smi` access. Fix folded into current cloud-init.
- Tailscale `tailscale up` was left manual per house rule (memory #17094).
- llama.cpp, llama-swap, and the whole inference stack were assembled by
  hand after VM build. Documented here for when we automate.

## 2026-04-22 — Evening migration to Ember

Ollama retired in favor of llama.cpp + llama-swap serving Unsloth GGUFs.
See memory #17122 (Rosemary's "disenforge" moment) for the architectural
shift — both Alpha and Rosemary converged on the OpenAI SDK, pointing at
Ember's `/v1` endpoint.

## 2026-04-23 — Rosemary goes live on Ember; matrix-based eviction deployed

Four models configured in llama-swap:
- `unsloth/qwen3.5-4b` (Q4_K_XL, ctx=16384, reasoning off)
- `gemma-3-12b-it` (Q4_K_XL, ctx=4096, q8_0 KV cache)
- `text-embedding-qwen3-embedding-4b` (Q4_K_M, ctx=2048, pooling=last)
- `text-embedding-nomic-embed-text-v1.5` (F16, ctx=2048, pooling=mean)

Key discoveries (full details in memory #17129, #17130):
1. Legacy `groups: swap: true` does NOT hard-evict across groups under VRAM
   pressure. Gemma load segfaulted because Qwen 3.5 wasn't being unloaded.
2. Matrix-based config fixes this: solver-based eviction with explicit sets
   and evict_costs. `rosemary_stack: "ne & g12"` and `alpha_stack: "qe & ne & q35"`
   with `ne` as a shared bridge member.
3. Can't co-resident all four on 12 GB 3080 Ti. Max realistic state is
   `[qe, ne, q35]` at ~9.3 GB or `[ne, g12]` at ~8.9 GB.

Traffic simulation test (`/Pondside/Workshop/Projects/ember-traffic/`):
- 40 turns mixed workload (30 Alpha + 10 Rosemary), 103 API calls, 199s wall.
- Zero errors, zero OOMs, zero segfaults after the matrix fix.
- Cold-load tax: ~6s per chat model swap, ~3-4s for qe, ~200ms for ne.
- Median VRAM: 8098 MiB, peak: 9303 MiB.

## 2026-04-23 — Pondside-Ops repo created

First commit captures the prototype VM's state:
- `domain.xml` dumped from current Primer-hosted Ember instance
- `llama-swap/config.yaml` copied from live `/etc/llama-swap/config.yaml`
- `cloud-init/user-data.yaml` drafted to fully reproduce the install steps
  that were done by hand on the prototype
- `motd` captures the first-login checklist

## Next: dogfood redeploy

Planned sequence:
1. Migrate `/opt/models/*` → `/mnt/models/` (virtiofs mount on Primer)
2. Hand Abe the spec for a fresh Ember build from this repo's `domain.xml`
3. Capture Abe's authoritative `virsh dumpxml` back to this repo
4. Destroy old Ember, deploy fresh from the captured state, verify service
5. Log result here
