from setuptools import setup

try:
    import Cython.Build
except:
    Cython = None

if Cython is None:
    ext_modules = None
else:
    ext_modules = Cython.Build.cythonize('cythonapp.pyx')

setup(
    name='cythonapp',
    py_modules=['cythonapp_test', 'pythonmodule'],
    ext_modules=ext_modules,
    setup_requires='Cython>=0.23.1',
)
