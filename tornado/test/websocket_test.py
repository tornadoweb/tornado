from __future__ import absolute_import, division, with_statement
import sys
import unittest

from tornado.websocket import unmask_frame_python
try:
    from tornado._websocket_unmask import unmask_frame as unmask_frame_c
except ImportError:
    unmask_frame_c = None

class MaskingTests(unittest.TestCase):
    def test_masking(self):
        if unmask_frame_c is None:
            raise TypeError('The optimized mask/unmask method is not available, skipping test')
        
        # make sure the C and Python versions produce the same result
        TEST_DATA = (
            ('1234567890', '1234'),
        )
        for (data, mask) in TEST_DATA:
            encoded1 = unmask_frame_python(data, mask).tostring()
            encoded2 = unmask_frame_c(data, mask)
            self.assertEquals(encoded1, encoded2)
            
            decoded1 = unmask_frame_python(encoded1, mask).tostring()
            decoded2 = unmask_frame_c(encoded2, mask)
            self.assertEquals(decoded1, data)
            self.assertEquals(decoded1, decoded2)
