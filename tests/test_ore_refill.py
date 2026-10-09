import struct
import unittest
from unittest.mock import patch
from ra3_auto import ore_refill


class OreIdentityTests(unittest.TestCase):
    def fixture(self):
        address, module, owner, template, array = 0x1000,0x2000,0x3000,0x4000,0x5000
        data=struct.pack('<11I',ore_refill.VTABLE,module,owner,0xc3a830,0xc35c44,
                         12500,0,0,0,1,30000)
        memory={address:data,module:struct.pack('<5I',0x8e220ee2,0xfee87083,100000,250,60),
                owner+4:struct.pack('<I',template),template+4:struct.pack('<II',0x942fff2d,0x212445f1),
                owner+0x320:struct.pack('<I',array),array:struct.pack('<32I',address,0,*([0]*30))}
        return address,memory

    def test_gathered_ore_is_subtracted_from_initial_value(self):
        address,memory=self.fixture()
        with patch.object(ore_refill.o,'read_mem',side_effect=lambda h,a,n:memory.get(a,b'')[:n]):
            result=ore_refill.node(None,address)
        self.assertEqual(17500,result['current'])
        self.assertEqual(30000,result['initial'])

    def test_detached_or_unrelated_object_is_not_a_write_target(self):
        for field in ('owner','array','module'):
            address,memory=self.fixture()
            if field=='owner':memory[0x4004]=struct.pack('<II',0x942fff2d,1234)
            elif field=='array':memory[0x5000]=bytes(128)
            else:memory[0x2000]=bytes(20)
            with patch.object(ore_refill.o,'read_mem',side_effect=lambda h,a,n:memory.get(a,b'')[:n]):
                with self.assertRaises(ValueError):ore_refill.node(None,address)

    def test_impossible_depletion_is_rejected(self):
        address,memory=self.fixture()
        raw=bytearray(memory[address]);struct.pack_into('<I',raw,0x14,30001);memory[address]=bytes(raw)
        with patch.object(ore_refill.o,'read_mem',side_effect=lambda h,a,n:memory.get(a,b'')[:n]):
            with self.assertRaises(ValueError):ore_refill.node(None,address)
