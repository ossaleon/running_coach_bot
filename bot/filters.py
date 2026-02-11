from telegram.ext import filters

from db import database as db


class _AuthorizedFilter(filters.UpdateFilter):
    async def filter(self, update) -> bool:
        if not update.effective_user:
            return False
        user = await db.get_user(update.effective_user.id)
        return user is not None and user.is_authorized


class _StravaLinkedFilter(filters.UpdateFilter):
    async def filter(self, update) -> bool:
        if not update.effective_user:
            return False
        user = await db.get_user(update.effective_user.id)
        return user is not None and user.is_authorized and user.has_strava


class _AssessmentDoneFilter(filters.UpdateFilter):
    async def filter(self, update) -> bool:
        if not update.effective_user:
            return False
        user = await db.get_user(update.effective_user.id)
        return user is not None and user.is_authorized and user.assessment_done


AUTHORIZED = _AuthorizedFilter()
STRAVA_LINKED = _StravaLinkedFilter()
ASSESSMENT_DONE = _AssessmentDoneFilter()
