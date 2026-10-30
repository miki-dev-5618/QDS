"""Hop job construction and execution accounting (no preparation labels at relays)."""
from dataclasses import replace
from .teleportation import TeleportJob, sample_channel_events


def hop_jobs(slot, edges, event, channel, injections, rng):
    jobs = []
    for index, edge in enumerate(edges):
        noise_event = sample_channel_events(1, rng, edge.depolarizing, 0.0)[0]
        hidden = injections.get(edge.id)
        attack_event = hidden.sample_events(1, rng)[0] if hidden else (None, None)
        # Existing session-wide experimental channel acts once at the first hop.
        # Declared edge channels act at EVERY hop, separately from injections.
        job = TeleportJob(slot.bit if index == 0 else 0, slot.basis if index == 0 else 0,
            slot.meas_basis, noise_pauli=noise_event[1], damping_gamma=edge.damping_gamma,
            is_lost=bool(rng.random() < edge.eta_loss))
        if index == 0:
            job = replace(job, eve_basis=event[0], extra_paulis=tuple(p for p in (event[1], attack_event[1]) if p),
                damping_gamma=channel.amp_damping_gamma, extra_damping_gamma=edge.damping_gamma,
                phase_damping_gamma=channel.phase_damping_gamma, damping_target=channel.damping_target,
                readout_p01=channel.readout_p01, readout_p10=channel.readout_p10,
                readout_location=channel.readout_location,
                cloner_type=(channel.cloner_type if (channel.noise_profile == "cloning" or channel.cloning_rate > 0.0)
                             and rng.random() < channel.cloning_rate else None),
                is_lost=job.is_lost or rng.random() < channel.eta_loss)
        else:
            job = replace(job, extra_paulis=tuple(p for p in (attack_event[1],) if p))
        if hidden:
            job = replace(job, eve_basis=attack_event[0] if attack_event[0] is not None else job.eve_basis,
                is_lost=job.is_lost or rng.random() < hidden.eta_loss)
        jobs.append(job)
        if job.is_lost:
            break
    return jobs


def count_traversal(edges, jobs, counters, router=None, digest=None):
    for edge, job in zip(edges, jobs):
        c = counters.setdefault(edge.id, {"attempted": 0, "received": 0, "lost": 0, "bell_pairs": 0})
        c["attempted"] += 1
        c["bell_pairs"] += 1  # consume-on-attempt, including heralded loss
        c["lost"] += int(job.is_lost)
        c["received"] += int(not job.is_lost)
        if router:
            router.traverse(edge, job.is_lost, digest)
        if job.is_lost:
            break
