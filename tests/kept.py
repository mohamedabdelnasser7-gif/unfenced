"""A kept lesson for the tests, by the real path: a person's own line (Lessons.add) goes on
trial like any other lesson, and a trial that proved itself keeps it (Lessons.keep). Tests
that need a lesson given in every case from the start use this; tests of the trial itself
use add() and the verdict."""


def kept_lesson(lessons, *args, **kw):
    """A person's line, added and kept at once; returns its id. Its stages must have no live
    trial, or it waits its turn and the test says so."""
    lesson_id = lessons.add(*args, **kw)
    if not lessons.keep(lesson_id):
        raise AssertionError(f"lesson {lesson_id} waits its turn behind a live trial, so it was not kept")
    return lesson_id
