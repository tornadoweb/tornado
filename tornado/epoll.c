/*
 * Copyright 2009 Facebook
 *
 * Licensed under the Apache License, Version 2.0 (the "License"); you may
 * not use this file except in compliance with the License. You may obtain
 * a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
 * License for the specific language governing permissions and limitations
 * under the License.
 */

#include "Python.h"
#include <string.h>
#include <sys/epoll.h>

#define MAX_EVENTS 24

/*
 * Simple wrapper around epoll_create.
 */
static PyObject* _epoll_create(void) {
    int fd = epoll_create(MAX_EVENTS);
    if (fd == -1) {
        PyErr_SetFromErrno(PyExc_Exception);
        return NULL;
    }

    return PyInt_FromLong(fd);
}

/*
 * Simple wrapper around epoll_ctl. We throw an exception if the call fails
 * rather than returning the error code since it is an infrequent (and likely
 * catastrophic) event when it does happen.
 */
static PyObject* _epoll_ctl(PyObject* self, PyObject* args) {
    int epfd, op, fd, events;
    struct epoll_event event;

    if (!PyArg_ParseTuple(args, "iiiI", &epfd, &op, &fd, &events)) {
        return NULL;
    }

    memset(&event, 0, sizeof(event));
    event.events = events;
    event.data.fd = fd;
    if (epoll_ctl(epfd, op, fd, &event) == -1) {
        PyErr_SetFromErrno(PyExc_OSError);
        return NULL;
    }

    Py_INCREF(Py_None);
    return Py_None;
}

/*
 * Simple wrapper around epoll_wait. We return None if the call times out and
 * throw an exception if an error occurs. Otherwise, we return a list of
 * (fd, event) tuples.
 */
static PyObject* _epoll_wait(PyObject* self, PyObject* args) {
    struct epoll_event events[MAX_EVENTS];
    int epfd, timeout, num_events, i;
    PyObject* list;
    PyObject* tuple;

    if (!PyArg_ParseTuple(args, "ii", &epfd, &timeout)) {
        return NULL;
    }

    Py_BEGIN_ALLOW_THREADS
    num_events = epoll_wait(epfd, events, MAX_EVENTS, timeout);
    Py_END_ALLOW_THREADS
    if (num_events == -1) {
        PyErr_SetFromErrno(PyExc_Exception);
        return NULL;
    }

    list = PyList_New(num_events);
    for (i = 0; i < num_events; i++) {
        tuple = PyTuple_New(2);
        PyTuple_SET_ITEM(tuple, 0, PyInt_FromLong(events[i].data.fd));
        PyTuple_SET_ITEM(tuple, 1, PyInt_FromLong(events[i].events));
        PyList_SET_ITEM(list, i, tuple);
    }
    return list;
}

/*
 * Our method declararations
 */
static PyMethodDef kEpollMethods[] = {
  {"epoll_create", (PyCFunction)_epoll_create, METH_NOARGS,
   "Create an epoll file descriptor"},
  {"epoll_ctl", _epoll_ctl, METH_VARARGS,
   "Control an epoll file descriptor"},
  {"epoll_wait", _epoll_wait, METH_VARARGS,
   "Wait for events on an epoll file descriptor"},
  {NULL, NULL, 0, NULL}
};

/*
 * Module initialization
 */
PyMODINIT_FUNC initepoll(void) {
    Py_InitModule("epoll", kEpollMethods);
}
