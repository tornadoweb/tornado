#include <Python.h>

#if PY_MAJOR_VERSION >= 3
#define IS_PY3K
#endif

/**
 * Mask/unmask WebSocket data frames.
 *
 * http://tools.ietf.org/html/rfc6455#section-5.3
 */
static PyObject *
Module_unmask_frame(PyObject *self, PyObject *args)
{
    unsigned char *input;
    unsigned int *input_multi;
    int input_length;
    unsigned int mask;
    unsigned char *mask_str;
    int mask_length;
    int i;
    PyObject *pyoutput;
    unsigned char *output;
    unsigned int *output_multi;
    
    if (!PyArg_ParseTuple(args, "s#s#", &input_multi, &input_length, &mask_str, &mask_length)) {
        return NULL;
    }
    
    if (mask_length != 4) {
        PyErr_Format(PyExc_TypeError, "the mask must be a string of length 4, not %d", mask_length);
        return NULL;
    } else if (input_length == 0) {
#ifdef IS_PY3K
        return PyByteArray_FromStringAndSize("", 0);
#else
        return PyString_FromString("");
#endif
    }

#ifdef IS_PY3K
    pyoutput = PyByteArray_FromStringAndSize(NULL, input_length);
#else
    pyoutput = PyString_FromStringAndSize(NULL, input_length);
#endif
    if (pyoutput == NULL) {
        return NULL;
    }
    
    mask = mask_str[3] << 24 | mask_str[2] << 16 | mask_str[1] << 8 | mask_str[0];
#ifdef IS_PY3K
    output_multi = (unsigned int *) PyByteArray_AS_STRING(pyoutput);
#else
    output_multi = (unsigned int *) PyString_AS_STRING(pyoutput);
#endif
    if (input_length >= 4) {
        // process 4 bytes at once
        for (i=0; i<input_length/4; i++) {
            *output_multi++ = *input_multi++ ^ mask;
        }
    }
    
    // process remaining bytes
    i = input_length & 3;
    if (i) {
        input = (unsigned char *) input_multi;
        output = (unsigned char *) output_multi;
        while (i--) {
            *output++ = *input++ ^ *mask_str++;
        }
    }
    return pyoutput;
}

PyMethodDef
methods[] = {
    {"unmask_frame",    (PyCFunction)Module_unmask_frame,   METH_VARARGS,   "Unmask WebSocket frame data."},
    {NULL, NULL, 0, NULL},
};

#ifdef IS_PY3K
static struct PyModuleDef
_websocket_unmask_module = {
   PyModuleDef_HEAD_INIT,
   "_websocket_unmask",
   NULL,
   -1,
   methods
};
#endif

PyMODINIT_FUNC
init_websocket_unmask(void)
{
#ifdef IS_PY3K
    return PyModule_Create(&_websocket_unmask_module);
#else
    Py_InitModule("_websocket_unmask", methods);
#endif
}
