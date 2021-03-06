# vim: ft=pyrex
import copy_reg

cimport cython
from libcpp.vector cimport vector as std_vector
from libcpp.string cimport string as std_string

cimport impl


cdef public enum SpecialChar:
    % for ch in SPECIAL_CHARS:
    ${ch} = impl.${ch}
    % endfor

cdef inline void check_impl_char(impl.Char special) except *:
    if special >= MaxCharUnaligned:
        raise ValueError("Unknown special character {}".format(special))


cdef inline const char* begin(bytes line):
    return line


cdef inline const char* end(bytes line):
    return (<const char*>line) + len(line)


cdef inline impl.ystring make_ystring(bytes line):
    return impl.ystring(begin(line), len(line))


cdef inline impl.yvector[impl.ystring] make_yvector_ystring(strings):
    cdef impl.yvector[impl.ystring] vec
    cdef Py_ssize_t size

    try:
        size = len(strings)
    except:
        pass
    else:
        vec.reserve(size)

    for s in strings:
        vec.push_back(<impl.ystring>make_ystring(s))
    return vec


cdef inline wrap_fsm(impl.Fsm fsm_impl):
    ret = Fsm()
    ret.fsm_impl.Swap(fsm_impl)
    return ret


cdef class Fsm:
    cdef impl.Fsm fsm_impl

    def __cinit__(self, Fsm copy=None):
        if copy is not None:
            self.fsm_impl = copy.fsm_impl

    @staticmethod
    def MakeFalse():
        return wrap_fsm(impl.Fsm_MakeFalse())

    def Size(self):
        return self.fsm_impl.Size()

    def Append(self, bytes line):
        self.fsm_impl.Append(make_ystring(line))
        return self

    def AppendSpecial(self, impl.Char ch):
        check_impl_char(ch)
        self.fsm_impl.AppendSpecial(ch)
        return self

    def AppendStrings(self, strings):
        self.fsm_impl.AppendStrings(make_yvector_ystring(strings))
        return self

    % for unary in FSM_INPLACE_UNARIES:
    def ${unary}(self):
        self.fsm_impl.${unary}()
        return self
    % endfor

    % for _, operation, _, rhs_type in FSM_BINARIES:
    <%
        unwrapped_rhs = "rhs.fsm_impl" if rhs_type == "Fsm" else "rhs"
        not_none = "not None" if rhs_type != "size_t" else ""
        inplace_op = "__i{}__".format(operation)
        explace_op = "__{}__".format(operation)
    %>
    def ${inplace_op}(self, ${rhs_type} rhs ${not_none}):
        self.fsm_impl.${inplace_op}(${unwrapped_rhs})
        return self

    def _${operation}(self, ${rhs_type} rhs ${not_none}):
        return wrap_fsm(self.fsm_impl.${explace_op}(${unwrapped_rhs}))

    def ${explace_op}(self, rhs):
        if isinstance(self, Fsm):
            return self._${operation}(rhs)
        return rhs.${explace_op}(self)  # __rmul__ mode, rhs is Fsm
    % endfor

    def Surrounded(self):
        return wrap_fsm(self.fsm_impl.Surrounded())

    def Iterated(self):
        return wrap_fsm(cython.operator.dereference(self.fsm_impl))

    def __invert__(self):
        return wrap_fsm(~self.fsm_impl)

    def Determine(self, size_t max_size=0):
        return self.fsm_impl.Determine(max_size)

    def IsDetermined(self):
        return self.fsm_impl.IsDetermined()

    def Compile(self, object scanner_class=None):
        if scanner_class is None:
            scanner_class = Scanner
        return scanner_class(self)



cdef class Lexer:
    cdef impl.yauto_ptr[impl.Lexer] lexer_impl

    def __cinit__(self, line=None, options=None):
        cdef:
            bytes utf8
            impl.yvector[impl.wchar32] ucs4

        if line is None:
            self.lexer_impl.reset(new impl.Lexer())
        else:
            if isinstance(line, unicode):
                utf8 = (<unicode>line).encode("utf8")
                ucs4 = impl.Utf8ToUcs4(begin(utf8), end(utf8))
                self.lexer_impl.reset(new impl.Lexer(ucs4))
            else:
                self.lexer_impl.reset(new impl.Lexer(begin(line), end(line)))

        if options is not None:
            if not isinstance(options, Options):
                options = Options.Parse(options)
            self.AddOptions(options)

    def AddOptions(self, Options options not None):
        options.Apply(self)
        return self

    def AddCapturing(self, size_t index):
        self.lexer_impl.get().AddFeature(impl.Capture(index))
        return self

    def Parse(self):
        return wrap_fsm(self.lexer_impl.get().Parse())



cdef class BaseState:
    pass


cdef class BaseScanner:
    pass


% for Scanner, spec in SCANNERS.items():
cdef class ${Scanner}State(BaseState):
    cdef readonly ${Scanner} scanner
    cdef impl.${Scanner}State state_impl

    def __cinit__(self, ${Scanner} scanner not None):
        self.scanner = scanner
        scanner.scanner_impl.Initialize(self.state_impl)

    % for method in ["Final", "__nonzero__"]:
    def ${method}(self):
        return self.scanner.scanner_impl.Final(self.state_impl)
    % endfor

    def Dead(self):
        return self.scanner.scanner_impl.Dead(self.state_impl)

    % if "AcceptedRegexps" not in spec.ignored_methods:
    def AcceptedRegexps(self):
        cdef:
            impl.ypair[const size_t*, const size_t*] span
            std_vector[size_t] regexps
        span = self.scanner.scanner_impl.AcceptedRegexps(self.state_impl)
        regexps.assign(span.first, span.second)
        return regexps
    % endif

    def Step(self, impl.Char ch):
        check_impl_char(ch)
        impl.Step(self.scanner.scanner_impl, self.state_impl, ch)
        return self

    % for method in ["Begin", "End"]:
    def ${method}(self):
        impl.Step(self.scanner.scanner_impl, self.state_impl, ${method}Mark)
        return self
    % endfor

    def Run(self, bytes line not None):
        impl.Run(self.scanner.scanner_impl, self.state_impl, begin(line), end(line))
        return self

    ScannerType = ${Scanner}

    % if Scanner == "CapturingScanner":
    def Captured(self):
        if self.state_impl.Captured():
            return self.state_impl.Begin(), self.state_impl.End()
        return None
    % endif

    % if Scanner == "CountingScanner":
    def Result(self, size_t index):
        return self.state_impl.Result(index)
    % endif


cdef inline object wrap_${Scanner}(impl.${Scanner} scanner_impl):
    ret = ${Scanner}()
    ret.scanner_impl.Swap(scanner_impl)
    return ret


def _${Scanner}_Load(bytes data not None):
    cdef:
        impl.yauto_ptr[impl.yistream] stream
        impl.${Scanner} loaded_scanner
    stream.reset(new impl.yistream(make_ystring(data)))
    loaded_scanner.Load(stream.get())
    return wrap_${Scanner}(loaded_scanner)


def _reduce_${Scanner}(instance):
    return _${Scanner}_Load, (instance.Save(),)
copy_reg.pickle(${Scanner}, _reduce_${Scanner})


cdef class ${Scanner}(BaseScanner):
    cdef impl.${Scanner} scanner_impl

    % if Scanner != "CountingScanner":
    def __cinit__(self, Fsm fsm=None):
        if fsm is not None:
            self.scanner_impl = impl.${Scanner}(fsm.fsm_impl)
    % else:
    def __cinit__(self, Fsm pattern=None, Fsm sep=None):
        if pattern is not None and sep is not None:
            self.scanner_impl = impl.CountingScanner(pattern.fsm_impl, sep.fsm_impl)
        elif pattern is not None or sep is not None:
            raise ValueError(
                "Expected both pattern and separator or neither, got only one of them"
            )
    % endif

    def Save(self):
        cdef impl.yostream stream
        self.scanner_impl.Save(&stream)
        return <std_string>stream.GetStr()

    Load = _${Scanner}_Load

    def InitState(self):
        return ${Scanner}State.__new__(${Scanner}State, self)

    % if "Glue" not in spec.ignored_methods:
    def GluedWith(self, ${Scanner} rhs not None, size_t max_size=0):
        cdef ${Scanner} glued = wrap_${Scanner}(
                impl.Glue(self.scanner_impl, rhs.scanner_impl, max_size)
        )
        if glued.Empty() and not (self.Empty() and rhs.Empty()):
            raise OverflowError("Too many regexps to glue")
        return glued
    % endif

    % for method in ["Size", "Empty", "RegexpsCount", "LettersCount"]:
    %     if method not in spec.ignored_methods:
    def ${method}(self):
        return self.scanner_impl.${method}()
    %     endif
    % endfor

    def Matches(self, bytes line not None):
        return impl.Matches(self. scanner_impl, begin(line), end(line))

    % for method in ["LongestPrefix", "ShortestPrefix"]:
    def ${method}(self, bytes line not None):
        cdef:
            const char* line_begin = begin(line)
            const char* line_end = end(line)
            const char* prefix_end
        prefix_end = impl.${method}(self.scanner_impl, line_begin, line_end)
        if prefix_end == NULL:
            return None
        return prefix_end - line_begin
    % endfor

    % for method in ["LongestSuffix", "ShortestSuffix"]:
    def ${method}(self, bytes line not None):
        cdef:
            const char* rbegin = end(line) - 1
            const char* rend = begin(line) - 1
            const char* suffix_begin
        suffix_begin = impl.${method}(self.scanner_impl, rbegin, rend)
        if suffix_begin == NULL:
            return None
        return suffix_begin - rend
    % endfor

    StateType = ${Scanner}State
% endfor



cdef class Options:
    cdef set option_set

    def __cinit__(self, set option_set=None):
        if option_set is None:
            option_set = set()
        self.option_set = option_set

    def __init__(self):
        pass

    @staticmethod
    def Parse(bytes letters not None):
        cdef parsed = Options()
        for letter in letters:
            parsed |= _LETTER_MAP[letter]
        return parsed

    def __ior__(self, Options rhs not None):
        self.option_set |= rhs.option_set
        return self

    def __or__(Options self not None, Options rhs not None):
        return Options.__new__(Options, self.option_set | rhs.option_set)

    cdef inline impl.yauto_ptr[impl.Options] Convert(self):
        return impl.ConvertFlagSetToOptions(<impl.FlagSet>self.option_set)

    cdef inline void Apply(self, Lexer lexer):
        cdef impl.yauto_ptr[impl.Options] converted = self.Convert()
        converted.get().Apply(cython.operator.dereference(lexer.lexer_impl))


% for option in OPTIONS:
${option} = Options.__new__(Options, set([impl.${option}]))
% endfor

_LETTER_MAP = {
    % for option, spec in OPTIONS.items():
    %     if spec.letter:
    "${spec.letter}": ${option},
    %     endif
    % endfor
}


cdef class Regexp:
    cdef impl.yauto_ptr[impl.Regexp] regexp_impl

    def __cinit__(self, pattern, Options options=None):
        cdef impl.yauto_ptr[impl.Options] converted_options
        if isinstance(pattern, Scanner):
            self.regexp_impl.reset(new impl.Regexp((<Scanner>pattern).scanner_impl))
        elif isinstance(pattern, SlowScanner):
            self.regexp_impl.reset(new impl.Regexp((<SlowScanner>pattern).scanner_impl))
        else:
            if options is None:
                options = Options()
            converted_options = options.Convert()
            self.regexp_impl.reset(
                new impl.Regexp(
                    make_ystring(pattern),
                    cython.operator.dereference(converted_options),
                )
            )

    % for matches in ["Matches", "__contains__"]:
    def ${matches}(self, bytes line not None):
        return self.regexp_impl.get().Matches(begin(line), end(line))
    % endfor
