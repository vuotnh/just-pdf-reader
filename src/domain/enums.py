"""Domain enums for the AI Ebook Reader platform."""

from enum import Enum


class BookFormat(Enum):
    """Supported ebook file formats."""

    PDF = "pdf"
    EPUB = "epub"
    AZW3 = "azw3"


class AnnotationType(Enum):
    """Types of annotations a user can create."""

    HIGHLIGHT = "highlight"
    UNDERLINE = "underline"
    NOTE = "note"
    COMMENT = "comment"


class HighlightColor(Enum):
    """Available highlight colors for annotations."""

    YELLOW = "yellow"
    GREEN = "green"
    BLUE = "blue"
    PINK = "pink"
    ORANGE = "orange"


class MasteryLevel(Enum):
    """Vocabulary mastery progression levels."""

    NEW = "new"
    LEARNING = "learning"
    REVIEWING = "reviewing"
    MASTERED = "mastered"


class Rating(Enum):
    """User rating for a review card response."""

    AGAIN = 1
    HARD = 2
    GOOD = 3
    EASY = 4


class SortCriterion(Enum):
    """Library sorting criteria."""

    TITLE = "title"
    AUTHOR = "author"
    DATE_ADDED = "date_added"
    LAST_READ = "last_read"
    FILE_SIZE = "file_size"


class CardType(Enum):
    """Review card presentation types."""

    FLASHCARD = "flashcard"
    CLOZE = "cloze"
    TYPING = "typing"
    MCQ = "mcq"


class SRAlgorithm(Enum):
    """Supported spaced repetition scheduling algorithms."""

    SM2 = "sm2"
    FSRS = "fsrs"
