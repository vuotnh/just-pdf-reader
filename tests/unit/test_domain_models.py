"""Unit tests for domain models, enums, and value objects."""

from datetime import datetime

import pytest

from src.domain.enums import (
    AnnotationType,
    BookFormat,
    CardType,
    HighlightColor,
    MasteryLevel,
    Rating,
    SortCriterion,
    SRAlgorithm,
)
from src.domain.models import (
    Annotation,
    Book,
    Bookmark,
    Collection,
    Comment,
    DictCache,
    KnowledgeLink,
    KnowledgeNode,
    ReadingHistory,
    ReviewCard,
    ReviewLog,
    Tag,
    VocabularyEntry,
)
from src.domain.value_objects import (
    BookFilter,
    DeckFilter,
    GraphFilter,
    ReadingPosition,
    TextPosition,
    VocabFilter,
)


class TestEnums:
    """Tests for domain enums."""

    def test_book_format_values(self):
        assert BookFormat.PDF.value == "pdf"
        assert BookFormat.EPUB.value == "epub"
        assert BookFormat.AZW3.value == "azw3"

    def test_annotation_type_values(self):
        assert AnnotationType.HIGHLIGHT.value == "highlight"
        assert AnnotationType.UNDERLINE.value == "underline"
        assert AnnotationType.NOTE.value == "note"
        assert AnnotationType.COMMENT.value == "comment"

    def test_highlight_color_values(self):
        assert HighlightColor.YELLOW.value == "yellow"
        assert HighlightColor.GREEN.value == "green"
        assert HighlightColor.BLUE.value == "blue"
        assert HighlightColor.PINK.value == "pink"
        assert HighlightColor.ORANGE.value == "orange"

    def test_mastery_level_values(self):
        assert MasteryLevel.NEW.value == "new"
        assert MasteryLevel.LEARNING.value == "learning"
        assert MasteryLevel.REVIEWING.value == "reviewing"
        assert MasteryLevel.MASTERED.value == "mastered"

    def test_rating_values(self):
        assert Rating.AGAIN.value == 1
        assert Rating.HARD.value == 2
        assert Rating.GOOD.value == 3
        assert Rating.EASY.value == 4

    def test_sort_criterion_values(self):
        assert SortCriterion.TITLE.value == "title"
        assert SortCriterion.AUTHOR.value == "author"
        assert SortCriterion.DATE_ADDED.value == "date_added"
        assert SortCriterion.LAST_READ.value == "last_read"
        assert SortCriterion.FILE_SIZE.value == "file_size"

    def test_card_type_values(self):
        assert CardType.FLASHCARD.value == "flashcard"
        assert CardType.CLOZE.value == "cloze"
        assert CardType.TYPING.value == "typing"
        assert CardType.MCQ.value == "mcq"

    def test_sr_algorithm_values(self):
        assert SRAlgorithm.SM2.value == "sm2"
        assert SRAlgorithm.FSRS.value == "fsrs"


class TestBookModel:
    """Tests for the Book dataclass."""

    def test_create_book_with_required_fields(self):
        book = Book(
            id="b1",
            title="Clean Code",
            file_path="/books/clean_code.pdf",
            file_hash="abc123",
            format=BookFormat.PDF,
        )
        assert book.id == "b1"
        assert book.title == "Clean Code"
        assert book.file_path == "/books/clean_code.pdf"
        assert book.file_hash == "abc123"
        assert book.format == BookFormat.PDF

    def test_book_optional_fields_default_to_none(self):
        book = Book(
            id="b1",
            title="Test",
            file_path="/a.pdf",
            file_hash="h",
            format=BookFormat.PDF,
        )
        assert book.author is None
        assert book.publisher is None
        assert book.language is None
        assert book.page_count is None
        assert book.cover_image is None

    def test_book_is_favorite_defaults_false(self):
        book = Book(
            id="b1",
            title="Test",
            file_path="/a.pdf",
            file_hash="h",
            format=BookFormat.PDF,
        )
        assert book.is_favorite is False

    def test_book_timestamps_auto_generated(self):
        book = Book(
            id="b1",
            title="Test",
            file_path="/a.pdf",
            file_hash="h",
            format=BookFormat.PDF,
        )
        assert isinstance(book.created_at, datetime)
        assert isinstance(book.updated_at, datetime)

    def test_book_with_all_fields(self):
        book = Book(
            id="b2",
            title="EPUB Book",
            file_path="/books/novel.epub",
            file_hash="def456",
            format=BookFormat.EPUB,
            author="Author Name",
            publisher="Publisher",
            language="en",
            page_count=300,
            cover_image="base64data",
            is_favorite=True,
        )
        assert book.author == "Author Name"
        assert book.publisher == "Publisher"
        assert book.language == "en"
        assert book.page_count == 300
        assert book.is_favorite is True


class TestAnnotationModel:
    """Tests for the Annotation dataclass."""

    def test_create_highlight_annotation(self):
        ann = Annotation(
            id="a1",
            book_id="b1",
            type=AnnotationType.HIGHLIGHT,
            selected_text="important text",
            position_data='{"page": 5, "start": 100, "end": 115}',
            color=HighlightColor.YELLOW,
        )
        assert ann.type == AnnotationType.HIGHLIGHT
        assert ann.color == HighlightColor.YELLOW
        assert ann.selected_text == "important text"

    def test_create_note_annotation(self):
        ann = Annotation(
            id="a2",
            book_id="b1",
            type=AnnotationType.NOTE,
            selected_text="passage",
            position_data='{"page": 10}',
            note_content="My thoughts on this.",
        )
        assert ann.type == AnnotationType.NOTE
        assert ann.note_content == "My thoughts on this."
        assert ann.color is None


class TestReviewCardModel:
    """Tests for the ReviewCard dataclass."""

    def test_review_card_defaults_fsrs(self):
        card = ReviewCard(id="c1", vocabulary_id="v1")
        assert card.algorithm == SRAlgorithm.FSRS
        assert card.difficulty == 5.0
        assert card.stability == 0.4
        assert card.ease_factor == 2.5
        assert card.repetitions == 0
        assert card.card_type == CardType.FLASHCARD

    def test_review_card_sm2_fields(self):
        card = ReviewCard(
            id="c2",
            vocabulary_id="v2",
            algorithm=SRAlgorithm.SM2,
            ease_factor=2.1,
            repetitions=3,
            last_interval=6.0,
        )
        assert card.algorithm == SRAlgorithm.SM2
        assert card.ease_factor == 2.1
        assert card.repetitions == 3
        assert card.last_interval == 6.0


class TestVocabularyEntryModel:
    """Tests for the VocabularyEntry dataclass."""

    def test_vocabulary_entry_defaults_new(self):
        entry = VocabularyEntry(
            id="v1",
            word="ephemeral",
            definition="lasting for a very short time",
        )
        assert entry.mastery_level == MasteryLevel.NEW
        assert entry.pronunciation is None
        assert entry.book_id is None

    def test_vocabulary_entry_full(self):
        entry = VocabularyEntry(
            id="v2",
            word="ubiquitous",
            definition="present everywhere",
            pronunciation="/juːˈbɪkwɪtəs/",
            part_of_speech="adjective",
            example_sentence="Smartphones are ubiquitous.",
            book_id="b1",
            position_data='{"page": 42}',
            mastery_level=MasteryLevel.LEARNING,
        )
        assert entry.mastery_level == MasteryLevel.LEARNING
        assert entry.part_of_speech == "adjective"


class TestValueObjects:
    """Tests for immutable value objects."""

    def test_text_position_frozen(self):
        pos = TextPosition(page=5, start_offset=10, end_offset=20)
        with pytest.raises(Exception):
            pos.page = 6  # type: ignore[misc]

    def test_reading_position_frozen(self):
        pos = ReadingPosition(chapter="ch1", scroll_offset=0.5)
        with pytest.raises(Exception):
            pos.chapter = "ch2"  # type: ignore[misc]

    def test_text_position_pdf(self):
        pos = TextPosition(page=10, start_offset=50, end_offset=75)
        assert pos.page == 10
        assert pos.chapter is None

    def test_text_position_epub(self):
        pos = TextPosition(chapter="chapter-3", start_offset=100, end_offset=200)
        assert pos.chapter == "chapter-3"
        assert pos.page is None

    def test_reading_position_defaults(self):
        pos = ReadingPosition()
        assert pos.page is None
        assert pos.chapter is None
        assert pos.scroll_offset == 0.0

    def test_book_filter_defaults(self):
        bf = BookFilter()
        assert bf.tag is None
        assert bf.collection_id is None
        assert bf.is_favorite is None
        assert bf.format is None
        assert bf.sort_by == SortCriterion.DATE_ADDED

    def test_book_filter_frozen(self):
        bf = BookFilter(tag="science")
        with pytest.raises(Exception):
            bf.tag = "fiction"  # type: ignore[misc]

    def test_vocab_filter(self):
        vf = VocabFilter(book_id="b1", mastery_level=MasteryLevel.NEW)
        assert vf.book_id == "b1"
        assert vf.mastery_level == MasteryLevel.NEW

    def test_deck_filter_defaults(self):
        df = DeckFilter()
        assert df.book_id is None
        assert df.card_types == []

    def test_graph_filter(self):
        gf = GraphFilter(tag="python", entity_types=["book", "annotation"])
        assert gf.tag == "python"
        assert gf.entity_types == ["book", "annotation"]


class TestRemainingModels:
    """Tests for Bookmark, Comment, Collection, Tag, ReadingHistory, KnowledgeNode, KnowledgeLink, DictCache."""

    def test_bookmark_creation(self):
        bm = Bookmark(id="bm1", book_id="b1", position_data='{"page": 42}', label="Important")
        assert bm.label == "Important"
        assert isinstance(bm.created_at, datetime)

    def test_comment_creation(self):
        c = Comment(id="cm1", annotation_id="a1", content="Great insight!")
        assert c.content == "Great insight!"

    def test_collection_creation(self):
        col = Collection(id="col1", name="Research Papers", description="My papers")
        assert col.name == "Research Papers"
        assert col.description == "My papers"

    def test_tag_creation(self):
        tag = Tag(id="t1", name="python", color="#3776ab")
        assert tag.name == "python"
        assert tag.color == "#3776ab"

    def test_reading_history_creation(self):
        rh = ReadingHistory(id="rh1", book_id="b1", position_data='{"page": 15}')
        assert rh.book_id == "b1"
        assert isinstance(rh.accessed_at, datetime)

    def test_knowledge_node_creation(self):
        node = KnowledgeNode(
            id="n1", entity_type="book", entity_id="b1", label="Clean Code"
        )
        assert node.entity_type == "book"
        assert node.label == "Clean Code"

    def test_knowledge_link_creation(self):
        link = KnowledgeLink(
            id="l1",
            source_node_id="n1",
            target_node_id="n2",
            link_type="backlink",
        )
        assert link.link_type == "backlink"
        assert isinstance(link.created_at, datetime)

    def test_dict_cache_creation(self):
        dc = DictCache(
            id="dc1",
            word="ephemeral",
            language="en",
            source="oxford",
            entry_json='{"definitions": ["lasting a short time"]}',
        )
        assert dc.word == "ephemeral"
        assert dc.source == "oxford"

    def test_review_log_creation(self):
        log = ReviewLog(
            id="rl1",
            card_id="c1",
            rating=Rating.GOOD,
            elapsed_days=3.5,
            scheduled_days=7.0,
            review_duration_ms=2500.0,
        )
        assert log.rating == Rating.GOOD
        assert log.elapsed_days == 3.5
        assert isinstance(log.reviewed_at, datetime)
