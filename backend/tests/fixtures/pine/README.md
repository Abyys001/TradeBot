# Pine corpus

`accept/` — scripts the v1 subset (Q24) must load. Every file parses, validates
with **no errors**, and runs 200 synthetic bars without raising. Between them
they touch every construct listed in `docs/bot-mode.md` §1.3.

`reject/` — one file per row of `apps/pine/subset.py:REJECTIONS`, plus the
semantic checks that are not in that table. The **last line** of each file is a
machine-readable expectation:

```
//@expect code=<error code> line=<1-based> col=<1-based>
```

It goes last so that adding it cannot move the line it points at. A rejection
without a fixture fails `test_pine_validate.py::test_every_rejection_has_a_fixture`
— that is the mechanism `bot-plan.md` §3 means by "a new rejection cannot ship
without its message".
