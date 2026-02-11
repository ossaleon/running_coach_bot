from enum import IntEnum, auto


class OnboardingState(IntEnum):
    PASSWORD = auto()


class AssessmentState(IntEnum):
    AGE = auto()
    GENDER = auto()
    EXPERIENCE = auto()
    WEEKLY_MILEAGE = auto()
    RECENT_RACE = auto()
    INJURY = auto()
    MAX_HR = auto()
    REST_HR = auto()
    PREFERRED_DAYS = auto()
    CONFIRM = auto()


class ObjectiveState(IntEnum):
    TYPE = auto()
    TARGET = auto()
    DATE = auto()
    CONFIRM = auto()


class FeedbackState(IntEnum):
    RPE = auto()
    COMMENTS = auto()
