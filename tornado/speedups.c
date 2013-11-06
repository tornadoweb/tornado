#include <Python.h>

static PyObject* websocket_mask(PyObject* self, PyObject* args) {
    const char* mask;
    int mask_len;
    const char* data;
    int data_len;
    int i;

    if (!PyArg_ParseTuple(args, "s#s#", &mask, &mask_len, &data, &data_len)) {
        return NULL;
    }

    PyObject* result = PyBytes_FromStringAndSize(NULL, data_len);
    if (!result) {
        return NULL;
    }
    char* buf = PyBytes_AsString(result);
    for (i = 0; i < data_len; i++) {
        buf[i] = data[i] ^ mask[i % 4];
    }

    return result;
}

static PyMethodDef methods[] = {
    {"websocket_mask",  websocket_mask, METH_VARARGS, ""},
    {NULL, NULL, 0, NULL}
};

#if PY_MAJOR_VERSION >= 3
static struct PyModuleDef speedupsmodule = {
   PyModuleDef_HEAD_INIT,
   "speedups",
   NULL,
   -1,
   methods
};

PyMODINIT_FUNC
PyInit_speedups() {
    return PyModule_Create(&speedupsmodule);
}
#else  // Python 2.x
PyMODINIT_FUNC
initspeedups() {
    Py_InitModule("tornado.speedups", methods);
}
#endif
