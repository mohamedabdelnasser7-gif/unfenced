# Red team levels round 1
*Created: 2026-11-04. Last updated: 2026-11-04.*

Red team on branch levels (5d6e6d9..de8b74a), scratch copy, fake data, no network. Filed by root from the hand-back; root read the cited lines.

1. CONFIRMED MEDIUM (HIGH if 16 of 20 is a hard floor), reflection/morning.py _level_gate with arena/levels.py needs(). The Connect gate scores the latest sealed run against the current level but with that run's own gate size, with no floor at the level's gate. A medium run of 10 test matches won 8 of 10 with no failed check, then raised to high, passes the high gate at 8 of 10 instead of 16 of 20 (DECISIONS 85). tests/test_levels_morning.py test_the_gate_size_comes_from_the_item pins this. Fix: the gate also needs gate size at least the level's gate; raising the level asks for a new run.

Ruled out: hand edited level.json (fails closed to high; only a valid lower level writes); replayed or forged run items (sealed, newest by time and file); request forgery on POST /arena/level (Host, Origin and token checked; bad level and unknown agent refused); a low run using the 1,500 cap; test customers leaked, duplicated or studied; a practice customer deciding the win (an independent judge decides).
