#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>
#include <string.h>

static PyObject *websocket_mask(PyObject *self, PyObject *const *args, Py_ssize_t nargs)
{
    Py_buffer mask_buf, data_buf;
    const unsigned char *mask;
    const unsigned char *data;
    unsigned char *buf;
    uint32_t uint32_mask;
    uint64_t uint64_mask;
    Py_ssize_t data_len;
    Py_ssize_t i;
    PyObject *result;

    if (nargs != 2)
    {
        PyErr_SetString(PyExc_TypeError, "websocket_mask() takes exactly 2 arguments");
        return NULL;
    }

    if (PyObject_GetBuffer(args[0], &mask_buf, PyBUF_SIMPLE) < 0)
    {
        return NULL;
    }
    if (mask_buf.len != 4)
    {
        PyBuffer_Release(&mask_buf);
        PyErr_SetString(PyExc_ValueError, "mask must be 4 bytes");
        return NULL;
    }
    if (PyObject_GetBuffer(args[1], &data_buf, PyBUF_SIMPLE) < 0)
    {
        PyBuffer_Release(&mask_buf);
        return NULL;
    }

    mask = mask_buf.buf;
    data = data_buf.buf;
    // Keep the length in a local whose address is never taken, so the
    // compiler can hold it in a register across the loop below.
    data_len = data_buf.len;

    result = PyBytes_FromStringAndSize(NULL, data_len);
    if (!result)
    {
        goto done;
    }
    buf = (unsigned char *)PyBytes_AsString(result);

    // Use memcpy for unaligned loads and stores; compilers turn these into
    // single instructions, and unlike pointer casts they are well-defined
    // regardless of alignment and aliasing. The 8-byte mask is the 4-byte
    // pattern repeated twice, so it is correct on any byte order.
    memcpy(&uint32_mask, mask, 4);
    uint64_mask = ((uint64_t)uint32_mask << 32) | uint32_mask;

    for (i = 0; i + 8 <= data_len; i += 8)
    {
        uint64_t chunk;
        memcpy(&chunk, data + i, 8);
        chunk ^= uint64_mask;
        memcpy(buf + i, &chunk, 8);
    }

    for (; i < data_len; i++)
    {
        buf[i] = data[i] ^ mask[i & 3];
    }

done:
    PyBuffer_Release(&data_buf);
    PyBuffer_Release(&mask_buf);
    return result;
}

static int speedups_exec(PyObject *module)
{
    return 0;
}

static PyMethodDef methods[] = {
    {"websocket_mask", (PyCFunction)(void (*)(void))websocket_mask, METH_FASTCALL, ""},
    {NULL, NULL, 0, NULL}};

static PyModuleDef_Slot slots[] = {
    {Py_mod_exec, speedups_exec},
#if (!defined(Py_LIMITED_API) && PY_VERSION_HEX >= 0x030c0000) || Py_LIMITED_API >= 0x030c0000
    {Py_mod_multiple_interpreters, Py_MOD_PER_INTERPRETER_GIL_SUPPORTED},
#endif
#if (!defined(Py_LIMITED_API) && PY_VERSION_HEX >= 0x030d0000) || Py_LIMITED_API >= 0x030d0000
    {Py_mod_gil, Py_MOD_GIL_NOT_USED},
#endif
    {0, NULL}};

static struct PyModuleDef speedupsmodule = {
    PyModuleDef_HEAD_INIT,
    "speedups",
    NULL,
    0,
    methods,
    slots,
};

PyMODINIT_FUNC
PyInit_speedups(void)
{
    return PyModuleDef_Init(&speedupsmodule);
}
