# encoding: utf-8
import pickle

import pytest

import pire_py as pire


SCANNER_CLASSES = [
    pire.Scanner,
    pire.ScannerNoMask,
    pire.NonrelocScanner,
    pire.NonrelocScannerNoMask,
    pire.SimpleScanner,
    pire.SlowScanner,
    pire.CapturingScanner,
]

SCANNERS_WITHOUT_GLUE = [
    pire.SimpleScanner,
    pire.SlowScanner,
    pire.CapturingScanner,
]


def check_scanner(scanner, accepts=(), rejects=()):
    for line in accepts:
        assert scanner.Matches(line), '"%s"' % line
    for line in rejects:
        assert not scanner.Matches(line), '"%s"' % line


def check_equivalence(scanner1, scanner2, examples):
    for line in examples:
        assert scanner1.Matches(line) == scanner2.Matches(line), '"%s"' % line


def check_state(state, final=None, dead=None, accepted_regexps=None):
    if dead is None and final:
        dead = False

    if accepted_regexps is None and final is False:
        accepted_regexps = ()
    if isinstance(state, (pire.SimpleScannerState, pire.CapturingScannerState)):
        accepted_regexps = None

    assert final is None or state.Final() == final
    assert dead is None or state.Dead() == dead
    assert accepted_regexps is None or tuple(state.AcceptedRegexps()) == tuple(accepted_regexps)


@pytest.fixture(params=SCANNER_CLASSES)
def scanner_class(request):
    return request.param


@pytest.fixture()
def parse_scanner(scanner_class):
    def scanner_factory(pattern, options=""):
        lexer = pire.Lexer(pattern, options)
        fsm = lexer.Parse()
        return scanner_class(fsm)
    return scanner_factory


@pytest.fixture()
def example_scanner(parse_scanner):
    return parse_scanner("s(om)*e")


def check_scanner_is_like_example_scanner(scanner):
    check_scanner(scanner, accepts=["se", "somome"], rejects=["", "s"])


class TestFsm(object):
    def test_fsm_is_default_constructible(self):
        f = pire.Fsm()
        assert 1 == f.Size()

    def test_fsm_can_be_made_false(self):
        f = pire.Fsm.MakeFalse()
        assert 1 == f.Size()

    def test_default_fsm_compiles_to_default_scanner(self):
        scanner = pire.Fsm().Compile()
        assert pire.Scanner == type(scanner)

    def test_fsm_compiles_to_scanner_of_choice(self, scanner_class):
        assert scanner_class == type(pire.Fsm().Compile(scanner_class))

    def test_fsm_is_copy_constructible(self):
        fsm = pire.Fsm().Append("ab")
        fsm_copy = pire.Fsm(fsm)
        assert fsm_copy is not fsm
        check_equivalence(
            fsm.Compile(),
            fsm_copy.Compile(),
            ["", "a", "ab", "ab-", "-"],
        )

        fsm.Append("c")
        assert not fsm_copy.Compile().Matches("abc")

    def test_fsm_supports_appending_special(self, scanner_class):
        fsm = pire.Fsm()
        fsm.AppendSpecial(pire.BeginMark)
        fsm.Append('a')
        fsm.AppendSpecial(pire.EndMark)

        scanner = scanner_class(fsm)
        state = scanner.InitState()

        check_state(state.Begin(), final=False, dead=False)
        check_state(state.Run('a'), final=False, dead=False)
        check_state(state.Step(pire.EndMark), final=True)

    def test_fsm_raises_when_appending_invalid_special(self):
        invalid_chars = [
            pire.MaxCharUnaligned,
            pire.MaxCharUnaligned + 2,
        ]
        fsm = pire.Fsm()
        for invalid_char in invalid_chars:
            with pytest.raises(ValueError):
                fsm.AppendSpecial(invalid_char)
        for not_convertible in [-1, -42, 2**200, 2**30]:
            with pytest.raises(OverflowError):
                fsm.AppendSpecial(not_convertible)

    def test_fsm_supports_appending_several_strings(self, scanner_class):
        fsm = pire.Fsm().Append("-")
        fsm.AppendStrings(["abc", "de"])
        check_scanner(
            scanner_class(fsm),
            accepts=["-abc", "-de"],
            rejects=["-", "abc", ""],
        )

    def test_fsm_supports_appending_generated_strings(self, scanner_class):
        import itertools
        fsm = pire.Fsm().Append("-")
        fsm.AppendStrings(itertools.imap(str, ["abc", "de"]))
        check_scanner(
            scanner_class(fsm),
            accepts=["-abc", "-de"],
            rejects=["-", "abc", ""],
        )

    def test_fsm_raises_when_one_of_appended_strings_is_empty(self):
        fsm = pire.Fsm()
        for invalid_strings in [[""], ["nonempty", ""]]:
            with pytest.raises(ValueError):
                fsm.AppendStrings(invalid_strings)

    def test_fsm_supports_fluent_inplace_operations(self, scanner_class, parse_scanner):
        a = pire.Fsm().Append("a").AppendDot()

        b = pire.Fsm()
        b.Append("b")

        d = pire.Fsm().Append("d")
        d *= 3

        c = pire.Lexer("c").Parse()

        fsm = a.Iterate()
        fsm += b.AppendAnything()
        fsm |= d
        fsm &= c.PrependAnything().Complement()

        expected_scanner = parse_scanner("((a.)*(b.*)|(d{3}))&~(.*c)", "a")

        check_equivalence(
            expected_scanner,
            scanner_class(fsm), [
                "ddd", "dddc", "a-b--c", "a-a-b--",
                "bdddc", "bddd", "", "b", "bc", "c",
            ]
        )

    def test_fsm_supports_nonmodifying_operations(self, scanner_class, parse_scanner):
        a, b, c, d, e = [pire.Lexer(char).Parse() for char in "abcde"]

        expression = ((a + b.Iterated()) | c.Surrounded() | (2 * (d * 2))) & ~e
        expected_scanner = parse_scanner("((ab*)|(.*c.*)|(d{4}))&~e", "a")

        check_equivalence(
            expected_scanner,
            scanner_class(expression), [
                "a", "abbbb", "c", "--c-",
                "dddd", "--", "e", "-ee-", "",
            ]
        )


class TestLexer(object):
    def test_lexer_default_constructible(self):
        lexer = pire.Lexer()
        assert pire.Fsm == type(lexer.Parse())

    def test_lexer_cannot_be_constructed_with_wrong_argument(self):
        with pytest.raises(TypeError):
            pire.Lexer(42)

    def test_lexer_parses_valid_regexp_right(self, parse_scanner):
        check_scanner(
            parse_scanner(""),
            accepts=[""],
            rejects=["some"],
        )
        check_scanner(
            parse_scanner("(2.*)&([0-9]*_1+)", "a"),
            accepts=["2123_1111", "2_1"],
            rejects=["123_1111", "2123_1111$", "^_1"],
        )
        check_scanner(
            parse_scanner("a|b|c"),
            accepts=["a", "b", "c"],
            rejects=["", "ab", "ac", "bc", "aa", "bb", "cc"],
        )

    def test_lexer_raises_on_parsing_invalid_regexp(self):
        lexer = pire.Lexer("[ab")
        with pytest.raises(ValueError):
            lexer.Parse()

    def test_lexer_accepts_unicode_pattern(self, parse_scanner):
        check_scanner(
            parse_scanner(u"юникод", "u"),
            accepts=["\xd1\x8e\xd0\xbd\xd0\xb8\xd0\xba\xd0\xbe\xd0\xb4"],
            rejects=["\xd1", ""],
        )


class TestScanner(object):
    def test_scanner_inherits_from_base_scanner(self, scanner_class):
        assert issubclass(scanner_class, pire.BaseScanner)

    def test_state_inherits_from_base_state(self, scanner_class):
        assert issubclass(scanner_class.StateType, pire.BaseState)

    def test_state_type_property_is_set_right(self, scanner_class):
        assert isinstance(scanner_class().InitState(), scanner_class.StateType)

    def test_scanner_is_default_constructible(self, scanner_class):
        scanner = scanner_class()
        assert scanner.Empty()
        if scanner_class is not pire.SlowScanner:
            assert 1 == scanner.Size()
        check_scanner(scanner, rejects=["", "some"])

    def test_scanner_raises_when_matching_not_string_but_stays_valid(self, example_scanner):
        for invalid_input in [None, False, True, 0, 42]:
            with pytest.raises(TypeError):
                example_scanner.Matches(invalid_input)
        check_scanner_is_like_example_scanner(example_scanner)

    def test_scanner_is_picklable(self, example_scanner):
        packed = pickle.dumps(example_scanner)
        unpacked = pickle.loads(packed)
        check_scanner_is_like_example_scanner(unpacked)

    def test_scanner_is_saveable_and_loadable(self, example_scanner):
        packed = example_scanner.Save()
        unpacked = example_scanner.__class__.Load(packed)
        check_scanner_is_like_example_scanner(unpacked)

    def test_scanner_raises_when_loading_from_invalid_data(self, scanner_class):
        invalid_data = "invalid"
        with pytest.raises(ValueError):
            scanner_class.Load(invalid_data)

        saved = scanner_class().Save()
        with pytest.raises(ValueError):
            scanner_class.Load(saved[1:])

    def test_scanner_finds_prefixes_and_suffixes(self, scanner_class):
        fsm = pire.Lexer("-->").Parse()
        any_occurence = scanner_class(~pire.Fsm.MakeFalse() + fsm)
        first_occurence = scanner_class(~fsm.Surrounded() + fsm)
        reverse_occurence = scanner_class(fsm.Reverse())

        text = "1234567890 --> middle --> end"
        assert 14 == first_occurence.LongestPrefix(text)
        assert 11 == reverse_occurence.LongestSuffix(text[:14])

        assert 25 == any_occurence.LongestPrefix(text)
        assert 22 == reverse_occurence.LongestSuffix(text[:25])

        assert 14 == first_occurence.ShortestPrefix(text)
        assert 11 == reverse_occurence.ShortestSuffix(text[:14])

        assert 14 == any_occurence.ShortestPrefix(text)
        assert 11 == reverse_occurence.ShortestSuffix(text[:14])

    def test_scanner_does_not_find_nonexistent_prefixes_and_suffixes(self, parse_scanner):
        scanner = parse_scanner("text")
        assert None is scanner.LongestPrefix("nonexistent")
        assert None is scanner.ShortestPrefix("nonexistent")
        assert None is scanner.LongestSuffix("nonexistent")
        assert None is scanner.ShortestSuffix("nonexistent")

    def test_glued_scanners_have_runnable_state(self, scanner_class, parse_scanner):
        if scanner_class in SCANNERS_WITHOUT_GLUE:
            return

        glued = parse_scanner("ab").GluedWith(parse_scanner("abcd$"))

        assert 2 == glued.RegexpsCount()

        state = glued.InitState()
        check_state(state, final=False, dead=False)
        check_state(state.Run("ab"), final=True, accepted_regexps=(0,))
        check_state(state.Run("cd"), final=False, dead=False)
        check_state(state.End(), final=True, accepted_regexps=(1,))
        check_state(state.Run("-"), final=False, dead=True)

        doubled = glued.GluedWith(glued)

        state = doubled.InitState()
        check_state(state.Run("ab"), final=True, accepted_regexps=(0, 2))
        check_state(state.Run("cd").End(), final=True, accepted_regexps=(1, 3))

    def test_gluing_too_many_scanners_raises(self, scanner_class):
        if scanner_class in SCANNERS_WITHOUT_GLUE:
            return

        many_patterns = [
            '/product/',
            '/catalog/',
            '/?(\?.*)?$',
            '/.*/a',
            '/.*/b',
            '/.*/c',
            '/.*/d',
            '/.*/e',
            '/.*/f',
            '/.*/g',
            '/.*/1234567891011',
            '/.*/qwertyuiopasdfgh',
            '/.*/do_it_yourself/'
            '/.*/doityourself/'
        ]

        with pytest.raises(OverflowError):
            scanner = scanner_class()
            for pattern in many_patterns:
                new_scanner = (
                    pire.Lexer("^" + pattern + ".*")
                        .Parse()
                        .Compile(scanner_class)
                )
                scanner = scanner.GluedWith(new_scanner)
                assert not scanner.Empty()
            assert scanner.RegexpsCount() == len(many_patterns)


    def test_gluing_two_empty_scanners_does_not_raise(self, scanner_class):
        if scanner_class not in SCANNERS_WITHOUT_GLUE:
            scanner_class().GluedWith(scanner_class())


    def test_state_remembers_its_scanner(self, scanner_class):
        scanner = scanner_class()
        state = scanner.InitState()
        assert state.scanner == scanner


class TestEasy(object):
    def test_options_have_only_default_constuctor(self):
        pire.Options()
        with pytest.raises(TypeError):
            pire.Options({1})

    def test_regexp_matches(self):
        re = pire.Regexp("(foo|bar)+", pire.I)
        assert "prefix fOoBaR suffix" in re
        assert "bla bla bla" not in re
        assert re.Matches("barfoo")

    def test_regexp_honors_utf8(self):
        re = pire.Regexp("^.$", pire.I | pire.UTF8)
        assert "\x41" in re  # "A", valid UTF-8 string
        assert "\x81" not in re  # invalid UTF-8 string
        assert u"Я".encode("utf8") in re

    def test_regexp_uses_two_features(self):
        re = pire.Regexp("^(a.c&.b.)$", pire.I | pire.ANDNOT)
        assert "abc" in re
        assert "ABC" in re
        assert "adc" not in re


class TestExtra(object):
    def test_lexer_glues_similar_glyphs(self):
        almost_regexp = u"rеgехр"  # 'е', 'х' and 'р' are cyrillic
        exactly_regexp = "regexp"  # all latin1
        for pattern in [almost_regexp, exactly_regexp]:
            scanner = pire.Lexer(
                pattern,
                pire.UTF8 | pire.GLUE_SIMILAR_GLYPHS,
            ).Parse().Compile()
            check_scanner(
                scanner,
                accepts=[exactly_regexp, almost_regexp.encode("utf8")],
            )

    def test_capturing_trivial(self):
        """
        This is the "Trivial" test from tests/capture_ut.cpp.
        """
        lexer = pire.Lexer(r"""google_id\s*=\s*['"]([a-z0-9]+)['"]\s*;""")
        fsm = lexer.AddOptions(pire.I).AddCapturing(1).Parse()
        scanner = fsm.Surround().Compile(pire.CapturingScanner)

        text = "google_id = 'abcde';"
        captured = scanner.InitState().Begin().Run(text).End().Captured()
        assert captured
        assert "abcde" == text[captured[0] - 1:captured[1] - 1]

        text = "var google_id = 'abcde'; eval(google_id);"
        captured = scanner.InitState().Begin().Run(text).End().Captured()
        assert captured
        assert "abcde" == text[captured[0] - 1:captured[1] - 1]

        text = "google_id != 'abcde';"
        captured = scanner.InitState().Begin().Run(text).End().Captured()
        assert None is captured

    def test_counting_scanner_is_default_constructible(self):
        fsm = pire.Fsm()
        pire.CountingScanner()

    def test_counting_scanner_raises_when_constructed_without_second_fsm(self):
        fsm = pire.Fsm()
        with pytest.raises(ValueError):
            pire.CountingScanner(fsm)
        with pytest.raises(ValueError):
            pire.CountingScanner(pattern=fsm)
        with pytest.raises(ValueError):
            pire.CountingScanner(sep=fsm)

    def test_counting_scanner_state_has_right_result(self):
        scanner = pire.CountingScanner(
            pattern=pire.Lexer("[a-z]+").Parse(),
            sep=pire.Lexer(r"\s").Parse(),
        )
        text = "abc def, abc def ghi, abc"
        state = scanner.InitState().Begin().Run(text).End()
        assert 3 == state.Result(0)

    def test_glued_counting_scanner_state_has_right_results(self):
        separator_fsm = pire.Lexer(".*").Parse()
        scanner1, scanner2 = [
            pire.CountingScanner(pire.Lexer(pattern).Parse(), separator_fsm)
            for pattern in ["[a-z]+", "[0-9]+"]
        ]
        glued = scanner1.GluedWith(scanner2)

        state = glued.InitState()
        state.Begin().Run("abc defg 123 jklmn 4567 opqrst").End()

        assert 4 == state.Result(0)
        assert 2 == state.Result(1)
