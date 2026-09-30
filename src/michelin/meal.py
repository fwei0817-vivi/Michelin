"""Stateless meal actions; callers own session state, storage saves remain explicit.

A future chat adapter may propose these same structured actions. This module does
not interpret natural language, authenticate identities, or write profile history.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from michelin.schemas import DinerProfile


class PeopleAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    diners: list[DinerProfile] = Field(max_length=6)
    action: Literal["add", "update", "remove", "load_preferences"]
    person: DinerProfile | None = None
    person_id: str | None = None
    saved: list[DinerProfile] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def valid_action(self):
        for people in (self.diners, self.saved):
            if len({p.id for p in people}) != len(people):
                raise ValueError("Person IDs must be unique")
        if self.action in {"add", "update"}:
            if self.person is None or self.person_id is not None or self.saved:
                raise ValueError("Add/update requires only person")
        elif self.action == "remove":
            if not self.person_id or self.person is not None or self.saved:
                raise ValueError("Remove requires only person_id")
        elif self.person is not None or self.person_id is not None:
            raise ValueError("Load preferences requires only saved profiles")
        return self


def apply_people_action(request: PeopleAction) -> list[DinerProfile]:
    people = {p.id: p for p in request.diners}
    person = request.person
    if request.action == "add":
        if person.id in people:
            raise ValueError("Person already at this meal; use update")
        people[person.id] = person
    elif request.action == "update":
        if person.id not in people:
            raise ValueError("Person is not at this meal")
        people[person.id] = person
    elif request.action == "remove":
        if request.person_id not in people:
            raise ValueError("Person is not at this meal")
        del people[request.person_id]
    else:
        for saved in request.saved:
            current = people.get(saved.id)
            # Existing participants keep all current hard restrictions and identity.
            # New participants start from their explicitly loaded saved snapshot.
            people[saved.id] = (
                current.model_copy(
                    update={
                        "likes": saved.likes,
                        "dislikes": saved.dislikes,
                        "max_spice": saved.max_spice,
                    }
                )
                if current
                else saved
            )
    if len(people) > 6:
        raise ValueError("At most six diners are supported; remove someone before loading more")
    return list(people.values())
