# SPDX-License-Identifier: GPL-3.0-or-later
import json
from pathlib import Path
import shutil
import subprocess
import unittest


class BusRecoveryTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is optional for hosted QML callback tests')
    def test_disconnect_clears_cached_history_countdown_and_reconnect_clears_error(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / 'qml/QuickShareBus.qml').read_text(encoding='utf8')
        functions = source[source.index('    function emptyStatus'):source.index('    function invoke')]
        functions += source[source.index('    function refresh'):source.index('    Component.onCompleted')]
        script = '''const vm=require('vm'),fs=require('fs');
const ctx={status:{ready:true,receiving:true,receivingSeconds:590,jobs:[{id:'old'}]},error:''};
ctx.root=ctx;ctx.I18n={tr:()=> 'offline'};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(0,'utf8'),ctx);
ctx.call=(method,args,ok,fail)=>fail('missing service');ctx.refresh();
const offline=JSON.parse(JSON.stringify({status:ctx.status,error:ctx.error}));
ctx.call=(method,args,ok,fail)=>ok(JSON.stringify({ready:true,receiving:false,receivingSeconds:0,jobs:[],error:''}));
ctx.refresh();process.stdout.write(JSON.stringify({offline,online:{status:ctx.status,error:ctx.error}}));'''
        result = subprocess.run(['node', '-e', script], input=functions, text=True,
                                capture_output=True, check=True, encoding='utf8')
        data = json.loads(result.stdout)
        self.assertFalse(data['offline']['status']['ready'])
        self.assertFalse(data['offline']['status']['receiving'])
        self.assertEqual(data['offline']['status']['receivingSeconds'], 0)
        self.assertEqual(data['offline']['status']['jobs'], [])
        self.assertEqual(data['offline']['error'], 'offline')
        self.assertTrue(data['online']['status']['ready'])
        self.assertEqual(data['online']['error'], '')
