from __future__ import annotations


def should_auto_advance(
    *,
    now: float,
    started_at: float,
    started_offset: float,
    position: float,
    last_position: float,
    duration: float,
    last_duration: float,
    known_duration: float,
    stopped_samples: int,
) -> bool:
    """Decide se uma faixa realmente terminou.

    A função é independente do Flask e do driver MCI para poder ser testada de
    forma determinística. Ela aceita tanto os dados atuais do leitor quanto os
    últimos valores válidos e a duração lida diretamente do TOC do CD.
    """

    if started_at <= 0 or stopped_samples < 2:
        return False

    elapsed = max(0.0, now - started_at)
    if elapsed < 1.2:
        return False

    effective_duration = max(0.0, duration or last_duration or known_duration)
    if effective_duration <= 0:
        return False

    estimated_position = max(0.0, started_offset) + elapsed
    effective_position = max(
        max(0.0, position),
        max(0.0, last_position),
        estimated_position,
    )

    near_end = effective_position >= max(0.0, effective_duration - 2.5)
    timer_reached_end = estimated_position >= max(0.0, effective_duration - 0.7)
    return near_end or timer_reached_end
