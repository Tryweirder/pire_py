from libcpp.vector cimport vector
from libcpp.pair cimport pair
from libcpp.set cimport set
from libcpp.string cimport string


cdef extern from "sstream" namespace "std" nogil:
    cdef cppclass istringstream:
        istringstream(const string&)

    cdef cppclass ostringstream:
        ostringstream()

        string GetStr "str"()


cdef extern from "memory" namespace "std" nogil:
    cdef cppclass auto_ptr[T]:
        auto_ptr()

        T* get()
        T& operator * ()

        void reset(T*)


cdef extern from "pire/pire.h" namespace "Pire" nogil:
    ctypedef vector yvector
    ctypedef pair ypair
    ctypedef set yset
    ctypedef string ystring

    ctypedef auto_ptr yauto_ptr

    ctypedef int wchar32

ctypedef istringstream yistream
ctypedef ostringstream yostream
