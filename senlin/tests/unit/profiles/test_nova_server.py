# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import base64
import copy

import mock
from oslo_utils import encodeutils
import six

from senlin.common import exception as exc
from senlin.profiles import base as profiles_base
from senlin.profiles.os.nova import server
from senlin.tests.unit.common import base
from senlin.tests.unit.common import utils


class TestNovaServerProfile(base.SenlinTestCase):

    def setUp(self):
        super(TestNovaServerProfile, self).setUp()

        self.context = utils.dummy_context()
        self.spec = {
            'type': 'os.nova.server',
            'version': '1.0',
            'properties': {
                'context': {},
                'adminPass': 'adminpass',
                'auto_disk_config': True,
                'availability_zone': 'FAKE_AZ',
                'block_device_mapping': [{
                    'device_name': 'FAKE_NAME',
                    'volume_size': 1000,
                }],
                'config_drive': False,
                'flavor': 'FLAV',
                'image': 'FAKE_IMAGE',
                'key_name': 'FAKE_KEYNAME',
                "metadata": {"meta var": "meta val"},
                'name': 'FAKE_SERVER_NAME',
                'networks': [{
                    'port': 'FAKE_PORT',
                    'fixed-ip': 'FAKE_IP',
                    'network': 'FAKE_NET',
                }],
                'personality': [{
                    'path': '/etc/motd',
                    'contents': 'foo',
                }],
                'scheduler_hints': {
                    'same_host': 'HOST_ID',
                },
                'security_groups': ['HIGH_SECURITY_GROUP'],
                'user_data': 'FAKE_USER_DATA',
            }
        }

    def test_init(self):
        profile = server.ServerProfile('t', self.spec)

        self.assertIsNone(profile.server_id)

    def test__validate_az(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.validate_azs.return_value = ['FAKE_AZ']
        profile._computeclient = cc

        res = profile._validate_az(mock.Mock(), 'FAKE_AZ')

        self.assertEqual('FAKE_AZ', res)
        cc.validate_azs.assert_called_once_with(['FAKE_AZ'])

    def test__validate_az_validate_driver_failure(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.validate_azs.side_effect = exc.InternalError(message='BANG.')
        profile._computeclient = cc

        ex = self.assertRaises(exc.InternalError,
                               profile._validate_az,
                               mock.Mock(), 'FAKE_AZ')
        self.assertEqual("BANG.", six.text_type(ex))
        cc.validate_azs.assert_called_once_with(['FAKE_AZ'])

    def test__validate_az_validate_not_found(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.validate_azs.return_value = []
        profile._computeclient = cc

        ex = self.assertRaises(exc.InvalidSpec,
                               profile._validate_az,
                               mock.Mock(), 'FAKE_AZ')
        self.assertEqual("The specified availability_zone 'FAKE_AZ' could "
                         "not be found", six.text_type(ex))
        cc.validate_azs.assert_called_once_with(['FAKE_AZ'])

    def test__validate_az_create_driver_failure(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.validate_azs.side_effect = exc.InternalError(message='BANG')
        profile._computeclient = cc

        ex = self.assertRaises(exc.EResourceCreation,
                               profile._validate_az,
                               mock.Mock(), 'FAKE_AZ', 'create')
        self.assertEqual("Failed in creating server: BANG.", six.text_type(ex))
        cc.validate_azs.assert_called_once_with(['FAKE_AZ'])

    def test__validate_az_create_not_found(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.validate_azs.return_value = []
        profile._computeclient = cc

        ex = self.assertRaises(exc.EResourceCreation,
                               profile._validate_az,
                               mock.Mock(), 'FAKE_AZ', 'create')
        self.assertEqual("Failed in creating server: The specified "
                         "availability_zone 'FAKE_AZ' could not be found.",
                         six.text_type(ex))
        cc.validate_azs.assert_called_once_with(['FAKE_AZ'])

    def test__validate_flavor_validate(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        x_flavor = mock.Mock(is_disabled=False)
        cc.flavor_find.return_value = x_flavor
        profile._computeclient = cc

        res = profile._validate_flavor(mock.Mock(), 'FAKE_FLAVOR')

        self.assertEqual(x_flavor, res)
        cc.flavor_find.assert_called_once_with('FAKE_FLAVOR', False)

    def test__validate_flavor_validate_driver_failure(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.flavor_find.side_effect = exc.InternalError(message='BANG.')
        profile._computeclient = cc

        ex = self.assertRaises(exc.InternalError,
                               profile._validate_flavor,
                               mock.Mock(), 'FAKE_FLAVOR')
        self.assertEqual("BANG.", six.text_type(ex))
        cc.flavor_find.assert_called_once_with('FAKE_FLAVOR', False)

    def test__validate_flavor_validate_not_found(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        err = exc.InternalError(code=404, message='BANG')
        cc.flavor_find.side_effect = err
        profile._computeclient = cc

        ex = self.assertRaises(exc.InvalidSpec,
                               profile._validate_flavor,
                               mock.Mock(), 'FLAV',)
        self.assertEqual("The specified flavor 'FLAV' could "
                         "not be found.", six.text_type(ex))
        cc.flavor_find.assert_called_once_with('FLAV', False)

    def test__validate_flavor_validate_disabled(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        x_flavor = mock.Mock(is_disabled=True)
        cc.flavor_find.return_value = x_flavor
        profile._computeclient = cc

        ex = self.assertRaises(exc.InvalidSpec,
                               profile._validate_flavor,
                               mock.Mock(), 'FLAV')
        self.assertEqual("The specified flavor 'FLAV' is disabled",
                         six.text_type(ex))
        cc.flavor_find.assert_called_once_with('FLAV', False)

    def test__validate_flavor_create_driver_failure(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.flavor_find.side_effect = exc.InternalError(message='BANG')
        profile._computeclient = cc

        ex = self.assertRaises(exc.EResourceCreation,
                               profile._validate_flavor,
                               mock.Mock(), 'FAKE_FLAVOR', 'create')
        self.assertEqual("Failed in creating server: BANG.", six.text_type(ex))
        cc.flavor_find.assert_called_once_with('FAKE_FLAVOR', False)

    def test__validate_flavor_create_not_found(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        err = exc.InternalError(code=404, message='BANG')
        cc.flavor_find.side_effect = err
        profile._computeclient = cc

        ex = self.assertRaises(exc.EResourceCreation,
                               profile._validate_flavor,
                               mock.Mock(), 'FLAV', 'create')
        self.assertEqual("Failed in creating server: BANG.", six.text_type(ex))
        cc.flavor_find.assert_called_once_with('FLAV', False)

    def test__validate_flavor_create_disabled(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        x_flavor = mock.Mock(is_disabled=True)
        cc.flavor_find.return_value = x_flavor
        profile._computeclient = cc

        ex = self.assertRaises(exc.EResourceCreation,
                               profile._validate_flavor,
                               mock.Mock(), 'FLAV', 'create')
        self.assertEqual("Failed in creating server: The specified flavor "
                         "'FLAV' is disabled.",
                         six.text_type(ex))
        cc.flavor_find.assert_called_once_with('FLAV', False)

    def test__validate_flavor_update_driver_failure(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.flavor_find.side_effect = exc.InternalError(message='BANG')
        profile._computeclient = cc
        node_obj = mock.Mock(physical_id='SERVER')

        ex = self.assertRaises(exc.EResourceUpdate,
                               profile._validate_flavor,
                               node_obj, 'FAKE_FLAVOR', 'update')

        self.assertEqual("Failed in updating server SERVER: BANG.",
                         six.text_type(ex))
        cc.flavor_find.assert_called_once_with('FAKE_FLAVOR', False)

    def test__validate_flavor_update_not_found(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        err = exc.InternalError(code=404, message='BANG')
        cc.flavor_find.side_effect = err
        profile._computeclient = cc
        node_obj = mock.Mock(physical_id='SERVER')

        ex = self.assertRaises(exc.EResourceUpdate,
                               profile._validate_flavor,
                               node_obj, 'FLAV', 'update')
        self.assertEqual("Failed in updating server SERVER: BANG.",
                         six.text_type(ex))
        cc.flavor_find.assert_called_once_with('FLAV', False)

    def test__validate_flavor_update_disabled(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        x_flavor = mock.Mock(is_disabled=True)
        cc.flavor_find.return_value = x_flavor
        profile._computeclient = cc
        node_obj = mock.Mock(physical_id='SERVER')

        ex = self.assertRaises(exc.EResourceUpdate,
                               profile._validate_flavor,
                               node_obj, 'FLAV', 'update')
        self.assertEqual("Failed in updating server SERVER: The specified "
                         "flavor 'FLAV' is disabled.",
                         six.text_type(ex))
        cc.flavor_find.assert_called_once_with('FLAV', False)

    def test__validate_image(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        x_image = mock.Mock()
        cc.image_find.return_value = x_image
        profile._computeclient = cc

        res = profile._validate_image(mock.Mock(), 'FAKE_IMAGE')

        self.assertEqual(x_image, res)
        cc.image_find.assert_called_once_with('FAKE_IMAGE', False)

    def test__validate_image_driver_failure_validate(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.image_find.side_effect = exc.InternalError(message='BANG')
        profile._computeclient = cc

        ex = self.assertRaises(exc.InternalError,
                               profile._validate_image,
                               mock.Mock(), 'IMAGE')
        self.assertEqual("BANG", six.text_type(ex))
        cc.image_find.assert_called_once_with('IMAGE', False)

    def test__validate_image_driver_failure_create(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.image_find.side_effect = exc.InternalError(message='BANG')
        profile._computeclient = cc

        ex = self.assertRaises(exc.EResourceCreation,
                               profile._validate_image,
                               mock.Mock(), 'IMAGE', 'create')

        self.assertEqual("Failed in creating server: BANG.", six.text_type(ex))
        cc.image_find.assert_called_once_with('IMAGE', False)

    def test__validate_image_driver_failure_update(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.image_find.side_effect = exc.InternalError(message='BANG')
        profile._computeclient = cc
        node_obj = mock.Mock(physical_id='SERVER')

        ex = self.assertRaises(exc.EResourceUpdate,
                               profile._validate_image,
                               node_obj, 'IMAGE', 'update')

        self.assertEqual("Failed in updating server SERVER: BANG.",
                         six.text_type(ex))
        cc.image_find.assert_called_once_with('IMAGE', False)

    def test__validate_image_not_found_validate(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.image_find.side_effect = exc.InternalError(code=404, message='BANG')
        profile._computeclient = cc

        ex = self.assertRaises(exc.InvalidSpec,
                               profile._validate_image,
                               mock.Mock(), 'FAKE_IMAGE')
        self.assertEqual("The specified image 'FAKE_IMAGE' could "
                         "not be found.", six.text_type(ex))
        cc.image_find.assert_called_once_with('FAKE_IMAGE', False)

    def test__validate_image_not_found_create(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.image_find.side_effect = exc.InternalError(code=404, message='BANG')
        profile._computeclient = cc

        ex = self.assertRaises(exc.EResourceCreation,
                               profile._validate_image,
                               mock.Mock(), 'FAKE_IMAGE', 'create')
        self.assertEqual("Failed in creating server: BANG.", six.text_type(ex))
        cc.image_find.assert_called_once_with('FAKE_IMAGE', False)

    def test__validate_image_not_found_update(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.image_find.side_effect = exc.InternalError(code=404, message='BANG')
        profile._computeclient = cc
        node_obj = mock.Mock(physical_id='SERVER')

        ex = self.assertRaises(exc.EResourceUpdate,
                               profile._validate_image,
                               node_obj, 'FAKE_IMAGE', 'update')

        self.assertEqual("Failed in updating server SERVER: BANG.",
                         six.text_type(ex))
        cc.image_find.assert_called_once_with('FAKE_IMAGE', False)

    def test__validate_keypair(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        x_keypair = mock.Mock()
        cc.keypair_find.return_value = x_keypair
        profile._computeclient = cc

        res = profile._validate_keypair(mock.Mock(), 'KEYPAIR')

        self.assertEqual(x_keypair, res)
        cc.keypair_find.assert_called_once_with('KEYPAIR', False)

    def test__validate_keypair_validate_driver_failure(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.keypair_find.side_effect = exc.InternalError(message='BANG.')
        profile._computeclient = cc

        ex = self.assertRaises(exc.InternalError,
                               profile._validate_keypair,
                               mock.Mock(), 'KEYPAIR')
        self.assertEqual("BANG.", six.text_type(ex))
        cc.keypair_find.assert_called_once_with('KEYPAIR', False)

    def test__validate_keypair_valide_not_found(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        err = exc.InternalError(code=404, message='BANG')
        cc.keypair_find.side_effect = err
        profile._computeclient = cc

        ex = self.assertRaises(exc.InvalidSpec,
                               profile._validate_keypair,
                               mock.Mock(), 'FAKE_KEYNAME')
        self.assertEqual("The specified key_name 'FAKE_KEYNAME' could "
                         "not be found.", six.text_type(ex))
        cc.keypair_find.assert_called_once_with('FAKE_KEYNAME', False)

    def test__validate_keypair_create_driver_failure(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.keypair_find.side_effect = exc.InternalError(message='BANG')
        profile._computeclient = cc

        ex = self.assertRaises(exc.EResourceCreation,
                               profile._validate_keypair,
                               mock.Mock(), 'KEYPAIR', 'create')
        self.assertEqual("Failed in creating server: BANG.", six.text_type(ex))
        cc.keypair_find.assert_called_once_with('KEYPAIR', False)

    def test__validate_keypair_create_not_found(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        err = exc.InternalError(code=404, message='BANG')
        cc.keypair_find.side_effect = err
        profile._computeclient = cc

        ex = self.assertRaises(exc.EResourceCreation,
                               profile._validate_keypair,
                               mock.Mock(), 'FAKE_KEYNAME', 'create')
        self.assertEqual("Failed in creating server: BANG.", six.text_type(ex))
        cc.keypair_find.assert_called_once_with('FAKE_KEYNAME', False)

    def test__validate_keypair_update_driver_failure(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.keypair_find.side_effect = exc.InternalError(message='BANG')
        profile._computeclient = cc
        node_obj = mock.Mock(physical_id='SERVER')

        ex = self.assertRaises(exc.EResourceUpdate,
                               profile._validate_keypair,
                               node_obj, 'KEYPAIR', 'update')
        self.assertEqual("Failed in updating server SERVER: BANG.",
                         six.text_type(ex))
        cc.keypair_find.assert_called_once_with('KEYPAIR', False)

    def test__validate_keypair_update_not_found(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        err = exc.InternalError(code=404, message='BANG')
        cc.keypair_find.side_effect = err
        profile._computeclient = cc
        node_obj = mock.Mock(physical_id='SERVER')

        ex = self.assertRaises(exc.EResourceUpdate,
                               profile._validate_keypair,
                               node_obj, 'FAKE_KEYNAME', 'update')
        self.assertEqual("Failed in updating server SERVER: BANG.",
                         six.text_type(ex))
        cc.keypair_find.assert_called_once_with('FAKE_KEYNAME', False)

    def test__validate_bdm(self):
        profile = server.ServerProfile('t', self.spec)

        res = profile._validate_bdm()

        self.assertIsNone(res)

    def test__validate_bdm_both_specified_validate(self):
        self.spec['properties']['block_device_mapping_v2'] = [{
            'source_type': 'XTYPE',
            'destination_type': 'YTYPE',
            'volume_size': 10
        }]
        profile = server.ServerProfile('t', self.spec)

        ex = self.assertRaises(exc.InvalidSpec,
                               profile._validate_bdm)

        self.assertEqual("Only one of 'block_device_mapping' or "
                         "'block_device_mapping_v2' can be specified, "
                         "not both", six.text_type(ex))

    def test__validate_bdm_both_specified_create(self):
        self.spec['properties']['block_device_mapping_v2'] = [{
            'source_type': 'XTYPE',
            'destination_type': 'YTYPE',
            'volume_size': 10
        }]
        profile = server.ServerProfile('t', self.spec)

        ex = self.assertRaises(exc.EResourceCreation,
                               profile._validate_bdm,
                               'create')

        self.assertEqual("Failed in creating server: Only one of "
                         "'block_device_mapping' or 'block_device_mapping_v2'"
                         " can be specified, not both.",
                         six.text_type(ex))

    def test_do_validate_all_passed(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.validate_azs.return_value = ['FAKE_AZ']
        x_flavor = mock.Mock(is_disabled=False, id='FLAV')
        cc.flavor_find.return_value = x_flavor
        x_image = mock.Mock()
        cc.image_find.return_value = x_image
        x_key = mock.Mock()
        cc.keypair_find.return_value = x_key
        profile._computeclient = cc

        res = profile.do_validate(mock.Mock())

        self.assertTrue(res)
        cc.validate_azs.assert_called_once_with(['FAKE_AZ'])
        cc.flavor_find.assert_called_once_with('FLAV', False)
        cc.image_find.assert_called_once_with('FAKE_IMAGE', False)
        cc.keypair_find.assert_called_once_with('FAKE_KEYNAME', False)

    def _stubout_profile(self, profile):
        image = mock.Mock(id='FAKE_IMAGE_ID')
        self.patchobject(profile, '_validate_image', return_value=image)
        flavor = mock.Mock(id='FAKE_FLAVOR_ID')
        self.patchobject(profile, '_validate_flavor', return_value=flavor)
        keypair = mock.Mock()
        keypair.name = 'FAKE_KEYNAME'
        self.patchobject(profile, '_validate_keypair', return_value=keypair)
        self.patchobject(profile, '_validate_bdm', return_value=None)

    def test_do_create(self):
        cc = mock.Mock()
        nc = mock.Mock()
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = cc
        profile._networkclient = nc
        self._stubout_profile(profile)

        test_server = mock.Mock(id='FAKE_NODE_ID', index=123,
                                cluster_id='FAKE_CLUSTER_ID',
                                data={
                                    'placement': {
                                        'zone': 'AZ1',
                                        'servergroup': 'SERVER_GROUP_1'
                                    }
                                })
        test_server.name = 'TEST_SERVER'
        net = mock.Mock(id='FAKE_NETWORK_ID')
        nc.network_get.return_value = net

        nova_server = mock.Mock(id='FAKE_NOVA_SERVER_ID')
        cc.server_create.return_value = nova_server

        server_id = profile.do_create(test_server)

        # assertion
        nc.network_get.assert_called_once_with('FAKE_NET')

        attrs = dict(
            adminPass='adminpass',
            auto_disk_config=True,
            # availability_zone='FAKE_AZ',
            block_device_mapping=[{
                'volume_size': 1000,
                'device_name': 'FAKE_NAME'
            }],
            config_drive=False,
            flavorRef='FAKE_FLAVOR_ID',
            imageRef='FAKE_IMAGE_ID',
            key_name='FAKE_KEYNAME',
            metadata={
                'cluster_id': 'FAKE_CLUSTER_ID',
                'cluster_node_id': 'FAKE_NODE_ID',
                'cluster_node_index': '123',
                'meta var': 'meta val'
            },
            name='FAKE_SERVER_NAME',
            networks=[{
                'fixed-ip': 'FAKE_IP',
                'port': 'FAKE_PORT',
                'uuid': 'FAKE_NETWORK_ID',
            }],
            personality=[{
                'path': '/etc/motd',
                'contents': 'foo'
            }],
            scheduler_hints={
                'same_host': 'HOST_ID',
                'group': 'SERVER_GROUP_1',
            },
            security_groups=[{'name': 'HIGH_SECURITY_GROUP'}],
            user_data='FAKE_USER_DATA',
            availability_zone='AZ1',
        )

        ud = encodeutils.safe_encode('FAKE_USER_DATA')
        attrs['user_data'] = encodeutils.safe_decode(base64.b64encode(ud))

        cc.server_create.assert_called_once_with(**attrs)
        self.assertEqual(nova_server.id, server_id)

    def test_do_create_invalid_image(self):
        profile = server.ServerProfile('s2', self.spec)
        err = exc.EResourceCreation(type='server', message='boom')
        mock_image = self.patchobject(profile, '_validate_image',
                                      side_effect=err)
        node_obj = mock.Mock()

        self.assertRaises(exc.EResourceCreation, profile.do_create, node_obj)

        mock_image.assert_called_once_with(node_obj, 'FAKE_IMAGE', 'create')

    def test_do_create_invalid_flavor(self):
        profile = server.ServerProfile('s2', self.spec)
        image = mock.Mock(id='IMAGE_ID')
        mock_image = self.patchobject(profile, '_validate_image',
                                      return_value=image)
        err = exc.EResourceCreation(type='server', message='boom')
        mock_flavor = self.patchobject(profile, '_validate_flavor',
                                       side_effect=err)
        node_obj = mock.Mock()

        self.assertRaises(exc.EResourceCreation, profile.do_create, node_obj)

        mock_image.assert_called_once_with(node_obj, 'FAKE_IMAGE', 'create')
        mock_flavor.assert_called_once_with(node_obj, 'FLAV', 'create')

    def test_do_create_invalid_keypair(self):
        profile = server.ServerProfile('s2', self.spec)
        image = mock.Mock(id='IMAGE_ID')
        mock_image = self.patchobject(profile, '_validate_image',
                                      return_value=image)
        flavor = mock.Mock(id='FLAVOR_ID')
        mock_flavor = self.patchobject(profile, '_validate_flavor',
                                       return_value=flavor)
        err = exc.EResourceCreation(type='server', message='boom')
        mock_kp = self.patchobject(profile, '_validate_keypair',
                                   side_effect=err)
        node_obj = mock.Mock()

        self.assertRaises(exc.EResourceCreation, profile.do_create, node_obj)

        mock_image.assert_called_once_with(node_obj, 'FAKE_IMAGE', 'create')
        mock_flavor.assert_called_once_with(node_obj, 'FLAV', 'create')
        mock_kp.assert_called_once_with(node_obj, 'FAKE_KEYNAME', 'create')

    def test_do_create_invalid_bdm(self):
        profile = server.ServerProfile('s2', self.spec)
        image = mock.Mock(id='IMAGE_ID')
        mock_image = self.patchobject(profile, '_validate_image',
                                      return_value=image)
        flavor = mock.Mock(id='FLAVOR_ID')
        mock_flavor = self.patchobject(profile, '_validate_flavor',
                                       return_value=flavor)
        keypair = mock.Mock()
        mock_keypair = self.patchobject(profile, '_validate_keypair',
                                        return_value=keypair)
        err = exc.EResourceCreation(type='server', message='boom')
        mock_bdm = self.patchobject(profile, '_validate_bdm', side_effect=err)
        node_obj = mock.Mock()

        self.assertRaises(exc.EResourceCreation, profile.do_create, node_obj)

        mock_image.assert_called_once_with(node_obj, 'FAKE_IMAGE', 'create')
        mock_flavor.assert_called_once_with(node_obj, 'FLAV', 'create')
        mock_keypair.assert_called_once_with(node_obj, 'FAKE_KEYNAME',
                                             'create')
        mock_bdm.assert_called_once_with('create')

    def test_do_create_port_and_fixedip_not_defined(self):
        cc = mock.Mock()
        nc = mock.Mock()
        nc.network_get.return_value = mock.Mock(id='FAKE_NETWORK_ID')
        node_obj = mock.Mock(id='FAKE_NODE_ID', data={}, index=123,
                             cluster_id='FAKE_CLUSTER_ID')
        spec = {
            'type': 'os.nova.server',
            'version': '1.0',
            'properties': {
                'flavor': 'FLAV',
                'image': 'FAKE_IMAGE',
                'key_name': 'FAKE_KEYNAME',
                'name': 'FAKE_SERVER_NAME',
                'networks': [{
                    'network': 'FAKE_NET'
                }]
            }
        }

        profile = server.ServerProfile('s2', spec)
        profile._computeclient = cc
        profile._networkclient = nc
        self._stubout_profile(profile)

        nova_server = mock.Mock(id='FAKE_NOVA_SERVER_ID')
        cc.server_create.return_value = nova_server

        server_id = profile.do_create(node_obj)

        attrs = dict(auto_disk_config=True,
                     flavorRef='FAKE_FLAVOR_ID',
                     imageRef='FAKE_IMAGE_ID',
                     key_name='FAKE_KEYNAME',
                     metadata={
                         'cluster_id': 'FAKE_CLUSTER_ID',
                         'cluster_node_id': 'FAKE_NODE_ID',
                         'cluster_node_index': '123',
                     },
                     name='FAKE_SERVER_NAME',
                     networks=[{'uuid': 'FAKE_NETWORK_ID'}])

        cc.server_create.assert_called_once_with(**attrs)
        self.assertEqual(nova_server.id, server_id)

    def test_do_create_server_attrs_not_defined(self):
        cc = mock.Mock()
        nc = mock.Mock()
        nc.network_get.return_value = mock.Mock(id='FAKE_NETWORK_ID')
        node_obj = mock.Mock(id='FAKE_NODE_ID', data={}, index=123,
                             cluster_id='FAKE_CLUSTER_ID')

        # Assume image/scheduler_hints/user_data were not defined in spec file
        spec = {
            'type': 'os.nova.server',
            'version': '1.0',
            'properties': {
                'flavor': 'FLAV',
                'name': 'FAKE_SERVER_NAME',
                'security_groups': ['HIGH_SECURITY_GROUP'],
            }
        }
        profile = server.ServerProfile('t', spec)
        profile._computeclient = cc
        profile._networkclient = nc
        self._stubout_profile(profile)

        nova_server = mock.Mock(id='FAKE_NOVA_SERVER_ID')
        cc.server_create.return_value = nova_server

        server_id = profile.do_create(node_obj)

        attrs = dict(auto_disk_config=True,
                     flavorRef='FAKE_FLAVOR_ID',
                     name='FAKE_SERVER_NAME',
                     metadata={
                         'cluster_id': 'FAKE_CLUSTER_ID',
                         'cluster_node_id': 'FAKE_NODE_ID',
                         'cluster_node_index': '123',
                     },
                     security_groups=[{'name': 'HIGH_SECURITY_GROUP'}])

        cc.server_create.assert_called_once_with(**attrs)
        self.assertEqual(nova_server.id, server_id)

    def test_do_create_obj_name_cluster_id_is_none(self):
        cc = mock.Mock()
        nc = mock.Mock()
        spec = {
            'type': 'os.nova.server',
            'version': '1.0',
            'properties': {
                'flavor': 'FLAV',
                'name': 'FAKE_SERVER_NAME',
                'security_groups': ['HIGH_SECURITY_GROUP'],
            }
        }
        profile = server.ServerProfile('t', spec)
        profile._computeclient = cc
        profile._networkclient = nc
        self._stubout_profile(profile)

        node_obj = mock.Mock(id='FAKE_NODE_ID', cluster_id=None, data={},
                             index=None)
        node_obj.name = None
        nova_server = mock.Mock(id='FAKE_NOVA_SERVER_ID')
        cc.server_create.return_value = nova_server

        server_id = profile.do_create(node_obj)

        attrs = dict(auto_disk_config=True,
                     flavorRef='FAKE_FLAVOR_ID',
                     name='FAKE_SERVER_NAME',
                     metadata={'cluster_node_id': 'FAKE_NODE_ID'},
                     security_groups=[{'name': 'HIGH_SECURITY_GROUP'}])

        cc.server_create.assert_called_once_with(**attrs)
        self.assertEqual(nova_server.id, server_id)

    def test_do_create_name_property_is_not_defined(self):
        cc = mock.Mock()
        nc = mock.Mock()
        nc.network_get.return_value = mock.Mock(id='FAKE_NETWORK_ID')
        spec = {
            'type': 'os.nova.server',
            'version': '1.0',
            'properties': {
                'flavor': 'FLAV',
                'security_groups': ['HIGH_SECURITY_GROUP'],
            }
        }
        profile = server.ServerProfile('t', spec)
        profile._computeclient = cc
        profile._networkclient = nc
        self._stubout_profile(profile)

        node_obj = mock.Mock(id='NODE_ID', cluster_id='', index=-1, data={})
        node_obj.name = 'TEST-SERVER'

        nova_server = mock.Mock(id='FAKE_NOVA_SERVER_ID')
        cc.server_create.return_value = nova_server

        server_id = profile.do_create(node_obj)

        attrs = dict(auto_disk_config=True,
                     flavorRef='FAKE_FLAVOR_ID',
                     name='TEST-SERVER',
                     metadata={'cluster_node_id': 'NODE_ID'},
                     security_groups=[{'name': 'HIGH_SECURITY_GROUP'}])

        cc.server_create.assert_called_once_with(**attrs)
        self.assertEqual(nova_server.id, server_id)

    def test_do_create_bdm_v2(self):
        cc = mock.Mock()
        nc = mock.Mock()
        nc.network_get.return_value = mock.Mock(id='FAKE_NETWORK_ID')
        bdm_v2 = [
            {
                'volume_size': 1,
                'uuid': '6ce0be68',
                'source_type': 'image',
                'destination_type': 'volume',
                'boot_index': 0,
            },
            {
                'volume_size': 2,
                'source_type': 'blank',
                'destination_type': 'volume',
            }
        ]
        spec = {
            'type': 'os.nova.server',
            'version': '1.0',
            'properties': {
                'flavor': 'FLAV',
                'name': 'FAKE_SERVER_NAME',
                'security_groups': ['HIGH_SECURITY_GROUP'],
                'block_device_mapping_v2': bdm_v2,
            }
        }
        profile = server.ServerProfile('t', spec)
        profile._computeclient = cc
        profile._networkclient = nc
        self._stubout_profile(profile)

        node_obj = mock.Mock(id='NODE_ID', cluster_id='', index=-1, data={})
        node_obj.name = None

        nova_server = mock.Mock(id='FAKE_NOVA_SERVER_ID')
        cc.server_create.return_value = nova_server

        # do it
        server_id = profile.do_create(node_obj)

        # assertions
        expected_volume = {
            'guest_format': None,
            'boot_index': 0,
            'uuid': '6ce0be68',
            'volume_size': 1,
            'device_name': None,
            'disk_bus': None,
            'source_type': 'image',
            'device_type': None,
            'destination_type': 'volume',
            'delete_on_termination': None
        }
        self.assertEqual(expected_volume,
                         profile.properties['block_device_mapping_v2'][0])

        attrs = dict(auto_disk_config=True,
                     flavorRef='FAKE_FLAVOR_ID',
                     name='FAKE_SERVER_NAME',
                     metadata={'cluster_node_id': 'NODE_ID'},
                     security_groups=[{'name': 'HIGH_SECURITY_GROUP'}],
                     block_device_mapping_v2=bdm_v2)

        cc.server_create.assert_called_once_with(**attrs)
        self.assertEqual(nova_server.id, server_id)

    def test_do_delete_ok(self):
        profile = server.ServerProfile('t', self.spec)

        cc = mock.Mock()
        cc.server_delete.return_value = None
        profile._computeclient = cc

        test_server = mock.Mock(physical_id='FAKE_ID')

        res = profile.do_delete(test_server)

        self.assertTrue(res)
        cc.server_delete.assert_called_once_with('FAKE_ID', True)
        cc.wait_for_server_delete.assert_called_once_with('FAKE_ID')

    def test_do_delete_ignore_missing_force(self):
        profile = server.ServerProfile('t', self.spec)

        cc = mock.Mock()
        profile._computeclient = cc

        test_server = mock.Mock(physical_id='FAKE_ID')

        res = profile.do_delete(test_server, ignore_missing=False, force=True)

        self.assertTrue(res)
        cc.server_force_delete.assert_called_once_with('FAKE_ID', False)
        cc.wait_for_server_delete.assert_called_once_with('FAKE_ID')

    def test_do_delete_no_physical_id(self):
        profile = server.ServerProfile('t', self.spec)
        test_server = mock.Mock(physical_id=None)

        res = profile.do_delete(test_server)

        self.assertTrue(res)

    def test_do_delete_with_delete_failure(self):
        cc = mock.Mock()
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = cc

        err = exc.InternalError(code=500, message='Nova Error')
        cc.server_delete.side_effect = err
        obj = mock.Mock(physical_id='FAKE_ID')

        # do it
        ex = self.assertRaises(exc.EResourceDeletion,
                               profile.do_delete, obj)

        self.assertEqual('Failed in deleting server FAKE_ID: Nova Error.',
                         six.text_type(ex))
        cc.server_delete.assert_called_once_with('FAKE_ID', True)
        self.assertEqual(0, cc.wait_for_server_delete.call_count)

    def test_do_delete_with_force_delete_failure(self):
        cc = mock.Mock()
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = cc

        err = exc.InternalError(code=500, message='Nova Error')
        cc.server_force_delete.side_effect = err
        obj = mock.Mock(physical_id='FAKE_ID')

        # do it
        ex = self.assertRaises(exc.EResourceDeletion,
                               profile.do_delete, obj, force=True)

        self.assertEqual('Failed in deleting server FAKE_ID: Nova Error.',
                         six.text_type(ex))
        cc.server_force_delete.assert_called_once_with('FAKE_ID', True)
        self.assertEqual(0, cc.wait_for_server_delete.call_count)

    def test_do_delete_wait_for_server_timeout(self):
        cc = mock.Mock()
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = cc

        obj = mock.Mock(physical_id='FAKE_ID')
        err = exc.InternalError(code=500, message='TIMEOUT')
        cc.wait_for_server_delete.side_effect = err

        # do it
        ex = self.assertRaises(exc.EResourceDeletion,
                               profile.do_delete, obj)

        self.assertEqual('Failed in deleting server FAKE_ID: TIMEOUT.',
                         six.text_type(ex))
        cc.server_delete.assert_called_once_with('FAKE_ID', True)
        cc.wait_for_server_delete.assert_called_once_with('FAKE_ID')

    def test__update_basic_properties_ok(self):
        obj = mock.Mock()
        cc = mock.Mock()
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = cc
        profile.server_id = 'FAKE_ID'
        new_spec = copy.deepcopy(self.spec)
        new_spec['properties']['name'] = 'TEST_SERVER'
        new_spec['properties']['metadata'] = {'new_key': 'new_value'}
        new_profile = server.ServerProfile('t', new_spec)

        res = profile._update_basic_properties(obj, new_profile)

        self.assertIsNone(res)
        cc.server_metadata_update.assert_called_once_with(
            'FAKE_ID', {'new_key': 'new_value'})
        cc.server_update.assert_called_once_with('FAKE_ID', name='TEST_SERVER')

    def test__update_basic_properties_nothing_changed(self):
        obj = mock.Mock()
        cc = mock.Mock()
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = cc
        profile.server_id = 'FAKE_ID'
        new_spec = copy.deepcopy(self.spec)
        new_profile = server.ServerProfile('t', new_spec)

        res = profile._update_basic_properties(obj, new_profile)

        self.assertIsNone(res)
        self.assertEqual(0, cc.server_metadata_update.call_count)
        self.assertEqual(0, cc.server_update.call_count)

    def test___update_basic_properties_update_metadata_failed(self):
        ex = exc.InternalError(code=500, message='Nova Error')

        obj = mock.Mock()
        profile = server.ServerProfile('t', self.spec)
        profile.server_id = 'FAKE_ID'
        cc = mock.Mock()
        cc.server_metadata_update.side_effect = ex
        profile._computeclient = cc
        new_spec = copy.deepcopy(self.spec)
        new_spec['properties']['metadata'] = {'new_key': 'new_value'}
        new_profile = server.ServerProfile('t', new_spec)

        ex = self.assertRaises(exc.InternalError,
                               profile._update_basic_properties,
                               obj, new_profile)

        self.assertEqual('Nova Error', six.text_type(ex))
        cc.server_metadata_update.assert_called_once_with(
            'FAKE_ID', {'new_key': 'new_value'})

    def test__update_basic_properties_update_name_failed(self):
        cc = mock.Mock()
        err = exc.InternalError(code=500, message='Nova Error')
        cc.server_update.side_effect = err
        obj = mock.Mock()
        profile = server.ServerProfile('t', self.spec)
        profile.server_id = 'FAKE_ID'
        profile._computeclient = cc
        # new profile with new name
        new_spec = copy.deepcopy(self.spec)
        new_spec['properties']['name'] = 'TEST_SERVER'
        new_profile = server.ServerProfile('t', new_spec)

        ex = self.assertRaises(exc.InternalError,
                               profile._update_basic_properties,
                               obj, new_profile)

        self.assertEqual('Nova Error', six.text_type(ex))
        cc.server_update.assert_called_once_with(
            'FAKE_ID', name='TEST_SERVER')
        self.assertEqual(0, cc.server_metadata_update.call_count)

    def test__update_basic_properties_name_to_none(self):
        obj = mock.Mock()
        obj.name = 'FAKE_OBJ_NAME'

        cc = mock.Mock()
        profile = server.ServerProfile('t', self.spec)
        profile.server_id = 'FAKE_ID'
        profile._computeclient = cc
        # new spec with name deleted
        new_spec = copy.deepcopy(self.spec)
        del new_spec['properties']['name']
        new_profile = server.ServerProfile('t', new_spec)

        res = profile._update_basic_properties(obj, new_profile)

        self.assertIsNone(res)
        cc.server_update.assert_called_once_with(
            'FAKE_ID', name='FAKE_OBJ_NAME')

    def test__update_basic_properties_metadata_to_none(self):
        obj = mock.Mock()
        cc = mock.Mock()
        profile = server.ServerProfile('t', self.spec)
        profile.server_id = 'FAKE_ID'
        profile._computeclient = cc
        # new profile with metadata removed
        new_spec = copy.deepcopy(self.spec)
        del new_spec['properties']['metadata']
        new_profile = server.ServerProfile('t', new_spec)

        res = profile._update_basic_properties(obj, new_profile)

        self.assertIsNone(res)
        cc.server_metadata_update.assert_called_once_with(
            'FAKE_ID', {})

    @mock.patch.object(server.ServerProfile, '_update_network')
    def test_do_update_network_successful_no_definition_overlap(
            self, mock_update_network):

        mock_update_network.return_value = True
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = mock.Mock()

        obj = mock.Mock()
        obj.physical_id = 'FAKE_ID'

        networks_delete = [{
            'port': 'FAKE_PORT',
            'fixed-ip': 'FAKE_IP',
            'network': 'FAKE_NET',
        }]
        new_networks = [{
            'port': 'FAKE_PORT_NEW',
            'fixed-ip': 'FAKE_IP_NEW',
            'network': 'FAKE_NET_NEW',
        }]
        new_spec = copy.deepcopy(self.spec)
        new_spec['properties']['networks'] = new_networks
        new_profile = server.ServerProfile('t', new_spec)

        res = profile.do_update(obj, new_profile)
        self.assertTrue(res)
        mock_update_network.assert_called_with(obj, new_networks,
                                               networks_delete)

    @mock.patch.object(server.ServerProfile, '_update_network')
    def test_do_update_network_successful_definition_overlap(
            self, mock_update_network):

        mock_update_network.return_value = True
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = mock.Mock()

        obj = mock.Mock()
        obj.physical_id = 'FAKE_ID'

        networks_delete = [{
            'port': 'FAKE_PORT',
            'fixed-ip': 'FAKE_IP',
            'network': 'FAKE_NET',
        }]
        new_networks = [{
            'port': 'FAKE_PORT_NEW',
            'fixed-ip': 'FAKE_IP_NEW',
            'network': 'FAKE_NET_NEW',
        }]
        new_spec = copy.deepcopy(self.spec)
        new_spec['properties']['networks'] = [new_networks[0],
                                              networks_delete[0]]
        new_profile = server.ServerProfile('t', new_spec)

        res = profile.do_update(obj, new_profile)
        self.assertTrue(res)
        mock_update_network.assert_called_with(obj, new_networks, [])

    def test_do_update_without_profile(self):
        profile = server.ServerProfile('t', self.spec)
        obj = mock.Mock()
        obj.physical_id = 'FAKE_ID'
        new_profile = None
        res = profile.do_update(obj, new_profile)
        self.assertFalse(res)

    def test_update_network(self):
        obj = mock.Mock(physical_id='FAKE_ID')
        cc = mock.Mock()
        nc = mock.Mock()
        server_obj = mock.Mock()
        net1 = mock.Mock(id='net1')
        net2 = mock.Mock(id='net2')
        existing_ports = [
            {
                'port_id': 'port1',
                'net_id': 'net1',
                'fixed_ips': [{'subnet_id': 'subnet1', 'ip_address': 'ip1'}]
            },
            {
                'port_id': 'port2',
                'net_id': 'net1',
                'fixed_ips': [{'subnet_id': 'subnet1',
                               'ip_address': 'ip-random2'}]
            },
            {
                'port_id': 'port3',
                'net_id': 'net2',
                'fixed_ips': [{'subnet_id': 'subnet2', 'ip_address': 'ip3'}]
            },
        ]
        deleted_networks = [
            {'fixed-ip': 'ip1', 'network': 'net1', 'port': None},
            {'fixed-ip': None, 'network': 'net1', 'port': None},
            {'fixed-ip': None, 'network': None, 'port': 'port3'}
        ]
        created_networks = [
            {'fixed-ip': 'ip2', 'network': 'net1', 'port': None},
            {'fixed-ip': None, 'network': 'net2', 'port': None},
            {'fixed-ip': None, 'network': None, 'port': 'port4'}
        ]
        cc.server_get.return_value = server_obj
        cc.server_interface_list.return_value = existing_ports
        nc.network_get.side_effect = [net1, net1, net1, net2]

        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = cc
        profile._networkclient = nc
        profile._update_network(obj, created_networks, deleted_networks)
        calls = [mock.call('port1', server_obj),
                 mock.call('port3', server_obj),
                 mock.call('port2', server_obj)]
        cc.server_interface_delete.assert_has_calls(calls)
        calls = [
            mock.call(
                server_obj, net_id='net1', fixed_ips=[{'ip_address': 'ip2'}]),
            mock.call(server_obj, net_id='net2'),
            mock.call(server_obj, port_id='port4'),
        ]
        cc.server_interface_create.assert_has_calls(calls)

    @mock.patch.object(server.ServerProfile, '_update_image')
    def test_do_update_image_succeeded(self, mock_update_image):
        obj = mock.Mock()
        obj.physical_id = 'FAKE_ID'

        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = mock.Mock()
        new_spec = copy.deepcopy(self.spec)
        new_spec['properties']['image'] = 'FAKE_IMAGE_NEW'
        new_profile = server.ServerProfile('t', new_spec)

        res = profile.do_update(obj, new_profile)
        self.assertTrue(res)
        mock_update_image.assert_called_with(obj, 'FAKE_IMAGE',
                                             'FAKE_IMAGE_NEW',
                                             'adminpass')

    # TODO(Yanyan Hu): remove this mock after admin_pass update
    # is completely supported.
    @mock.patch.object(profiles_base.Profile, 'validate_for_update')
    @mock.patch.object(server.ServerProfile, '_update_image')
    def test_do_update_image_with_passwd(self, mock_update_image,
                                         mock_validate):
        obj = mock.Mock(physical_id='FAKE_ID')
        mock_validate.return_value = True
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = mock.Mock()
        new_spec = copy.deepcopy(self.spec)
        new_spec['properties']['image'] = 'FAKE_IMAGE_NEW'
        new_spec['properties']['adminPass'] = 'adminpass2'
        new_profile = server.ServerProfile('t', new_spec)
        res = profile.do_update(obj, new_profile)
        self.assertTrue(res)
        mock_update_image.assert_called_with(obj, 'FAKE_IMAGE',
                                             'FAKE_IMAGE_NEW',
                                             'adminpass2')

        del new_spec['properties']['adminPass']
        new_profile = server.ServerProfile('t', new_spec)
        self.assertIsNone(new_profile.properties['adminPass'])
        res = profile.do_update(obj, new_profile)
        self.assertTrue(res)
        mock_update_image.assert_called_with(obj, 'FAKE_IMAGE',
                                             'FAKE_IMAGE_NEW',
                                             'adminpass')

    @mock.patch.object(server.ServerProfile, '_update_image')
    def test_do_update_image_failed(self, mock_update_image):
        ex = exc.InternalError(code=404, message='Image Not Found')
        mock_update_image.side_effect = ex
        obj = mock.Mock(physical_id='FAKE_ID')

        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = mock.Mock()
        new_spec = copy.deepcopy(self.spec)
        new_spec['properties']['image'] = 'FAKE_IMAGE_NEW'
        new_profile = server.ServerProfile('t', new_spec)

        ex = self.assertRaises(exc.EResourceUpdate,
                               profile.do_update,
                               obj, new_profile)

        mock_update_image.assert_called_with(
            obj, 'FAKE_IMAGE', 'FAKE_IMAGE_NEW', 'adminpass')
        self.assertEqual('Failed in updating server FAKE_ID: Image Not Found.',
                         six.text_type(ex))

    @mock.patch.object(server.ServerProfile, '_update_flavor')
    def test_do_update_update_flavor_succeeded(self, mock_update_flavor):
        obj = mock.Mock(physical_id='FAKE_ID')
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = mock.Mock()
        new_spec = copy.deepcopy(self.spec)
        new_spec['properties']['flavor'] = 'FAKE_FLAVOR_NEW'
        new_profile = server.ServerProfile('t', new_spec)

        res = profile.do_update(obj, new_profile)
        self.assertTrue(res)
        mock_update_flavor.assert_called_with(obj, 'FLAV', 'FAKE_FLAVOR_NEW')

    @mock.patch.object(server.ServerProfile, '_update_flavor')
    def test_do_update__update_flavor_failed(self, mock_update_flavor):
        ex = exc.InternalError(code=404, message='Flavor Not Found')
        mock_update_flavor.side_effect = ex
        obj = mock.Mock(physical_id='FAKE_ID')
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = mock.Mock()
        new_spec = copy.deepcopy(self.spec)
        new_spec['properties']['flavor'] = 'FAKE_FLAVOR_NEW'
        new_profile = server.ServerProfile('t', new_spec)

        ex = self.assertRaises(exc.EResourceUpdate,
                               profile.do_update,
                               obj, new_profile)

        mock_update_flavor.assert_called_with(obj, 'FLAV', 'FAKE_FLAVOR_NEW')
        self.assertEqual('Failed in updating server FAKE_ID: '
                         'Flavor Not Found.',
                         six.text_type(ex))

    def test__update_flavor(self):
        obj = mock.Mock(physical_id='FAKE_ID')
        cc = mock.Mock()
        cc.flavor_find.side_effect = [
            mock.Mock(id='123'), mock.Mock(id='456')]
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = cc

        profile._update_flavor(obj, 'old_flavor', 'new_flavor')

        cc.flavor_find.has_calls(
            [mock.call('old_flavor'), mock.call('new_flavor')])
        cc.server_resize.assert_called_once_with('FAKE_ID', '456')
        cc.wait_for_server.has_calls([
            mock.call('FAKE_ID', 'VERIFY_RESIZE'),
            mock.call('FAKE_ID', 'ACTIVE')])
        cc.server_resize_confirm.assert_called_once_with('FAKE_ID')

    def test__update_flavor_resize_failed(self):
        obj = mock.Mock(physical_id='FAKE_ID')
        cc = mock.Mock()
        cc.flavor_find.side_effect = [
            mock.Mock(id='123'), mock.Mock(id='456')]
        cc.server_resize.side_effect = [
            exc.InternalError(code=500, message='Resize failed')]
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = cc

        ex = self.assertRaises(exc.InternalError,
                               profile._update_flavor,
                               obj, 'old_flavor', 'new_flavor')

        cc.server_resize.assert_called_once_with('FAKE_ID', '456')
        cc.server_resize_revert.assert_called_once_with('FAKE_ID')
        cc.wait_for_server.assert_called_once_with('FAKE_ID', 'ACTIVE')
        self.assertEqual('Resize failed', six.text_type(ex))

    def test__update_flavor_first_wait_for_server_failed(self):
        obj = mock.Mock(physical_id='FAKE_ID')
        cc = mock.Mock()
        cc.flavor_find.side_effect = [
            mock.Mock(id='123'), mock.Mock(id='456')]
        cc.wait_for_server.side_effect = [
            exc.InternalError(code=500, message='TIMEOUT'),
            None
        ]
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = cc

        # do it
        ex = self.assertRaises(exc.InternalError,
                               profile._update_flavor,
                               obj, 'old_flavor', 'new_flavor')

        # assertions
        cc.server_resize.assert_called_once_with('FAKE_ID', '456')
        cc.wait_for_server.has_calls([
            mock.call('FAKE_ID', 'VERIFY_RESIZE'),
            mock.call('FAKE_ID', 'ACTIVE')])
        cc.server_resize_revert.assert_called_once_with('FAKE_ID')
        self.assertEqual('TIMEOUT', six.text_type(ex))

    def test__update_flavor_resize_failed_revert_failed(self):
        obj = mock.Mock(physical_id='FAKE_ID')
        cc = mock.Mock()
        cc.flavor_find.side_effect = [
            mock.Mock(id='123'), mock.Mock(id='456')]
        err_resize = exc.InternalError(code=500, message='Resize')
        cc.server_resize.side_effect = err_resize
        err_revert = exc.InternalError(code=500, message='Revert')
        cc.server_resize_revert.side_effect = err_revert
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = cc

        # do it
        ex = self.assertRaises(exc.InternalError,
                               profile._update_flavor,
                               obj, 'old_flavor', 'new_flavor')

        # assertions
        cc.server_resize.assert_called_once_with('FAKE_ID', '456')
        cc.server_resize_revert.assert_called_once_with('FAKE_ID')
        # the wait_for_server wasn't called
        self.assertEqual(0, cc.wait_for_server.call_count)
        self.assertEqual('Revert', six.text_type(ex))

    def test__update_flavor_confirm_failed(self):
        obj = mock.Mock(physical_id='FAKE_ID')
        cc = mock.Mock()
        cc.flavor_find.side_effect = [
            mock.Mock(id='123'), mock.Mock(id='456')]
        err_confirm = exc.InternalError(code=500, message='Confirm')
        cc.server_resize_confirm.side_effect = err_confirm
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = cc

        # do it
        ex = self.assertRaises(exc.InternalError,
                               profile._update_flavor,
                               obj, 'old_flavor', 'new_flavor')

        # assertions
        cc.server_resize.assert_called_once_with('FAKE_ID', '456')
        cc.server_resize_confirm.assert_called_once_with('FAKE_ID')
        cc.wait_for_server.assert_called_once_with('FAKE_ID', 'VERIFY_RESIZE')
        self.assertEqual('Confirm', six.text_type(ex))

    def test__update_flavor_wait_confirm_failed(self):
        obj = mock.Mock(physical_id='FAKE_ID')
        cc = mock.Mock()
        cc.flavor_find.side_effect = [
            mock.Mock(id='123'), mock.Mock(id='456')]
        err_wait = exc.InternalError(code=500, message='Wait')
        cc.wait_for_server.side_effect = [None, err_wait]
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = cc

        # do it
        ex = self.assertRaises(exc.InternalError,
                               profile._update_flavor,
                               obj, 'old_flavor', 'new_flavor')

        # assertions
        cc.server_resize.assert_called_once_with('FAKE_ID', '456')
        cc.server_resize_confirm.assert_called_once_with('FAKE_ID')
        cc.wait_for_server.assert_has_calls([
            mock.call('FAKE_ID', 'VERIFY_RESIZE'),
            mock.call('FAKE_ID', 'ACTIVE')
        ])
        self.assertEqual('Wait', six.text_type(ex))

    def test_update_image(self):
        obj = mock.Mock(physical_id='FAKE_ID')
        mock_old_image = mock.Mock(id='123')
        mock_new_image = mock.Mock(id='456')
        cc = mock.Mock()
        cc.image_find.side_effect = [mock_old_image, mock_new_image]

        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = cc
        profile._update_image(obj, 'old_image', 'new_image', 'adminpass')
        cc.image_find.has_calls([
            mock.call('old_image'), mock.call('new_image')
        ])
        cc.server_rebuild.assert_called_once_with('FAKE_ID', '456',
                                                  'FAKE_SERVER_NAME',
                                                  'adminpass')
        cc.wait_for_server.assert_called_once_with('FAKE_ID', 'ACTIVE')

    def test_update_image_old_image_is_none(self):
        obj = mock.Mock(physical_id='FAKE_ID')
        cc = mock.Mock()
        mock_server = mock.Mock()
        mock_server.image = {
            'id': '123',
            'link': {
                'href': 'http://openstack.example.com/openstack/images/123',
                'rel': 'bookmark'
            }
        }
        cc.server_get.return_value = mock_server
        mock_image = mock.Mock(id='456')
        cc.image_find.return_value = mock_image

        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = cc
        profile._update_image(obj, None, 'new_image', 'adminpass')
        cc.image_find.assert_called_once_with('new_image')
        cc.server_get.assert_called_once_with('FAKE_ID')
        cc.server_rebuild.assert_called_once_with('FAKE_ID', '456',
                                                  'FAKE_SERVER_NAME',
                                                  'adminpass')
        cc.wait_for_server.assert_called_once_with('FAKE_ID', 'ACTIVE')

    def test_update_image_new_image_is_none(self):
        obj = mock.Mock(physical_id='FAKE_ID')
        cc = mock.Mock()
        mock_image = mock.Mock(id='123')
        cc.image_find.return_value = mock_image

        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = cc
        ex = self.assertRaises(exc.InternalError,
                               profile._update_image,
                               obj, 'old_image', None, 'adminpass')
        msg = ("Updating Nova server with image set to None is not "
               "supported by Nova.")
        self.assertEqual(msg, six.text_type(ex))
        cc.image_find.assert_called_once_with('old_image')

    def test_do_update_no_physical_id(self):
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = mock.Mock()
        node_obj = mock.Mock(physical_id=None)
        new_profile = mock.Mock()

        # Test path where server doesn't exist
        res = profile.do_update(node_obj, new_profile)

        self.assertFalse(res)

    def test_do_get_details(self):
        cc = mock.Mock()
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = cc
        node_obj = mock.Mock(physical_id='FAKE_ID')

        # Test normal path
        nova_server = mock.Mock()
        nova_server.to_dict.return_value = {
            'OS-DCF:diskConfig': 'MANUAL',
            'OS-EXT-AZ:availability_zone': 'nova',
            'OS-EXT-STS:power_state': 1,
            'OS-EXT-STS:task_state': None,
            'OS-EXT-STS:vm_state': 'active',
            'OS-SRV-USG:launched_at': 'TIMESTAMP1',
            'OS-SRV-USG:terminated_at': None,
            'accessIPv4': 'FAKE_IPV4',
            'accessIPv6': 'FAKE_IPV6',
            'addresses': {
                'private': [{
                    'OS-EXT-IPS-MAC:mac_addr': 'fa:16:3e:5e:00:81',
                    'version': 4,
                    'addr': '10.0.0.3',
                    'OS-EXT-IPS:type': 'fixed'
                }]
            },
            'config_drive': True,
            'created': 'CREATED_TIMESTAMP',
            'flavor': {
                'id': '1',
                'links': [{
                    'href': 'http://url_flavor',
                    'rel': 'bookmark'
                }]
            },
            'hostId': 'FAKE_HOST_ID',
            'id': 'FAKE_ID',
            'image': {
                'id': 'FAKE_IMAGE',
                'links': [{
                    'href': 'http://url_image',
                    'rel': 'bookmark'
                }],
            },
            'key_name': 'FAKE_KEY',
            'links': [{
                'href': 'http://url1',
                'rel': 'self'
            }, {
                'href': 'http://url2',
                'rel': 'bookmark'
            }],
            'metadata': {},
            'name': 'FAKE_NAME',
            'os-extended-volumes:volumes_attached': [],
            'progress': 0,
            'security_groups': [{'name': 'default'}],
            'status': 'FAKE_STATUS',
            'tenant_id': 'FAKE_TENANT',
            'updated': 'UPDATE_TIMESTAMP',
            'user_id': 'FAKE_USER_ID',
        }
        cc.server_get.return_value = nova_server
        res = profile.do_get_details(node_obj)
        expected = {
            'OS-DCF:diskConfig': 'MANUAL',
            'OS-EXT-AZ:availability_zone': 'nova',
            'OS-EXT-STS:power_state': 1,
            'OS-EXT-STS:task_state': '-',
            'OS-EXT-STS:vm_state': 'active',
            'OS-SRV-USG:launched_at': 'TIMESTAMP1',
            'OS-SRV-USG:terminated_at': '-',
            'accessIPv4': 'FAKE_IPV4',
            'accessIPv6': 'FAKE_IPV6',
            'config_drive': True,
            'created': 'CREATED_TIMESTAMP',
            'flavor': '1',
            'hostId': 'FAKE_HOST_ID',
            'id': 'FAKE_ID',
            'image': 'FAKE_IMAGE',
            'key_name': 'FAKE_KEY',
            'metadata': {},
            'name': 'FAKE_NAME',
            'os-extended-volumes:volumes_attached': [],
            'addresses': {
                'private': [{
                    'OS-EXT-IPS-MAC:mac_addr': 'fa:16:3e:5e:00:81',
                    'version': 4,
                    'addr': '10.0.0.3',
                    'OS-EXT-IPS:type': 'fixed'
                }]
            },
            'progress': 0,
            'security_groups': 'default',
            'updated': 'UPDATE_TIMESTAMP',
            'status': 'FAKE_STATUS',
        }
        self.assertEqual(expected, res)
        cc.server_get.assert_called_once_with('FAKE_ID')

    def test_do_get_details_with_no_network_or_sg(self):
        cc = mock.Mock()
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = cc
        node_obj = mock.Mock(physical_id='FAKE_ID')

        # Test normal path
        nova_server = mock.Mock()
        nova_server.to_dict.return_value = {
            'addresses': {},
            'flavor': {
                'id': 'FAKE_FLAVOR',
            },
            'id': 'FAKE_ID',
            'image': {
                'id': 'FAKE_IMAGE',
            },
            'security_groups': [],
        }
        cc.server_get.return_value = nova_server
        res = profile.do_get_details(node_obj)
        expected = {
            'flavor': 'FAKE_FLAVOR',
            'id': 'FAKE_ID',
            'image': 'FAKE_IMAGE',
            'addresses': {},
            'security_groups': '',
        }
        self.assertEqual(expected, res)
        cc.server_get.assert_called_once_with('FAKE_ID')

    def test_do_get_details_with_more_network_or_sg(self):
        cc = mock.Mock()
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = cc
        node_obj = mock.Mock(physical_id='FAKE_ID')

        # Test normal path
        nova_server = mock.Mock()
        nova_server.to_dict.return_value = {
            'addresses': {
                'private': [{
                    'version': 4,
                    'addr': '10.0.0.3',
                }, {
                    'version': 4,
                    'addr': '192.168.43.3'
                }],
                'public': [{
                    'version': 4,
                    'addr': '172.16.5.3',
                }]
            },
            'flavor': {
                'id': 'FAKE_FLAVOR',
            },
            'id': 'FAKE_ID',
            'image': {
                'id': 'FAKE_IMAGE',
            },
            'security_groups': [{
                'name': 'default',
            }, {
                'name': 'webserver',
            }],
        }
        cc.server_get.return_value = nova_server
        res = profile.do_get_details(node_obj)
        expected = {
            'flavor': 'FAKE_FLAVOR',
            'id': 'FAKE_ID',
            'image': 'FAKE_IMAGE',
            'addresses': {
                'private': [{
                    'version': 4,
                    'addr': '10.0.0.3',
                }, {
                    'version': 4,
                    'addr': '192.168.43.3'
                }],
                'public': [{
                    'version': 4,
                    'addr': '172.16.5.3',
                }]
            },
            'security_groups': ['default', 'webserver'],
        }
        self.assertEqual(expected, res)
        cc.server_get.assert_called_once_with('FAKE_ID')

    def test_do_get_details_no_physical_id(self):
        # Test path for server not created
        profile = server.ServerProfile('t', self.spec)
        node_obj = mock.Mock(physical_id='')
        self.assertEqual({}, profile.do_get_details(node_obj))

        node_obj.physical_id = None
        self.assertEqual({}, profile.do_get_details(node_obj))

    def test_do_get_details_server_not_found(self):
        # Test path for server not created
        cc = mock.Mock()
        err = exc.InternalError(code=404, message='No Server found for ID')
        cc.server_get.side_effect = err
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = cc
        node_obj = mock.Mock(physical_id='FAKE_ID')

        res = profile.do_get_details(node_obj)
        expected = {
            'Error': {
                'message': 'No Server found for ID',
                'code': 404
            }
        }
        self.assertEqual(expected, res)
        cc.server_get.assert_called_once_with('FAKE_ID')

    def test_do_join_successful(self):
        profile = server.ServerProfile('t', self.spec)

        cluster_id = "FAKE_CLUSTER_ID"
        cc = mock.Mock()
        cc.server_metadata_get.return_value = {'FOO': 'BAR'}
        cc.server_metadata_update.return_value = {'cluster_id': cluster_id}
        profile._computeclient = cc

        node_obj = mock.Mock(physical_id='FAKE_ID', index=567)

        res = profile.do_join(node_obj, cluster_id)

        self.assertTrue(res)
        cc.server_metadata_get.assert_called_once_with('FAKE_ID')
        expected_metadata = {
            'cluster_id': 'FAKE_CLUSTER_ID',
            'cluster_node_index': '567',
            'FOO': 'BAR'
        }
        cc.server_metadata_update.assert_called_once_with(
            'FAKE_ID', expected_metadata)

    def test_do_join_server_not_created(self):
        # Test path where server not specified
        profile = server.ServerProfile('t', self.spec)
        node_obj = mock.Mock(physical_id=None)

        res = profile.do_join(node_obj, 'FAKE_CLUSTER_ID')

        self.assertFalse(res)

    def test_do_leave_successful(self):
        # Test normal path
        cc = mock.Mock()
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = cc

        node_obj = mock.Mock(physical_id='FAKE_ID')

        res = profile.do_leave(node_obj)

        self.assertTrue(res)
        cc.server_metadata_delete.assert_called_once_with(
            'FAKE_ID', ['cluster_id', 'cluster_node_index'])

    def test_do_leave_no_physical_id(self):
        profile = server.ServerProfile('t', self.spec)
        node_obj = mock.Mock(physical_id=None)

        res = profile.do_leave(node_obj)

        self.assertFalse(res)

    def test_do_rebuild(self):
        profile = server.ServerProfile('t', self.spec)
        x_image = {'id': '123'}
        x_server = mock.Mock(image=x_image)
        cc = mock.Mock()
        cc.server_get.return_value = x_server
        cc.server_rebuild.return_value = True
        profile._computeclient = cc
        node_obj = mock.Mock(physical_id='FAKE_ID')

        res = profile.do_rebuild(node_obj)

        self.assertTrue(res)
        cc.server_get.assert_called_with('FAKE_ID')
        cc.server_rebuild.assert_called_once_with('FAKE_ID', '123',
                                                  'FAKE_SERVER_NAME',
                                                  'adminpass')
        cc.wait_for_server.assert_called_once_with('FAKE_ID', 'ACTIVE')

    def test_do_rebuild_server_not_found(self):

        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        err = exc.InternalError(code=404, message='FAKE_ID not found')
        cc.server_get.side_effect = err
        profile._computeclient = cc
        node_obj = mock.Mock(physical_id='FAKE_ID')

        ex = self.assertRaises(exc.EResourceOperation,
                               profile.do_rebuild,
                               node_obj)

        self.assertEqual('Failed in rebuilding server FAKE_ID: '
                         'FAKE_ID not found',
                         six.text_type(ex))
        cc.server_get.assert_called_once_with('FAKE_ID')

    def test_do_rebuild_failed_rebuild(self):
        profile = server.ServerProfile('t', self.spec)
        x_image = {'id': '123'}
        x_server = mock.Mock(image=x_image)
        cc = mock.Mock()
        cc.server_get.return_value = x_server
        ex = exc.InternalError(code=500, message='cannot rebuild')
        cc.server_rebuild.side_effect = ex
        profile._computeclient = cc
        node_obj = mock.Mock(physical_id='FAKE_ID')

        ex = self.assertRaises(exc.EResourceOperation,
                               profile.do_rebuild,
                               node_obj)

        self.assertEqual('Failed in rebuilding server FAKE_ID: '
                         'cannot rebuild',
                         six.text_type(ex))
        cc.server_get.assert_called_once_with('FAKE_ID')
        cc.server_rebuild.assert_called_once_with('FAKE_ID', '123',
                                                  'FAKE_SERVER_NAME',
                                                  'adminpass')
        self.assertEqual(0, cc.wait_for_server.call_count)

    def test_do_rebuild_failed_waiting(self):
        profile = server.ServerProfile('t', self.spec)
        x_image = {'id': '123'}
        x_server = mock.Mock(image=x_image)
        cc = mock.Mock()
        cc.server_get.return_value = x_server
        ex = exc.InternalError(code=500, message='timeout')
        cc.wait_for_server.side_effect = ex
        profile._computeclient = cc
        node_obj = mock.Mock(physical_id='FAKE_ID')

        ex = self.assertRaises(exc.EResourceOperation,
                               profile.do_rebuild,
                               node_obj)

        self.assertEqual('Failed in rebuilding server FAKE_ID: timeout',
                         six.text_type(ex))
        cc.server_get.assert_called_once_with('FAKE_ID')
        cc.server_rebuild.assert_called_once_with('FAKE_ID', '123',
                                                  'FAKE_SERVER_NAME',
                                                  'adminpass')
        cc.wait_for_server.assert_called_once_with('FAKE_ID', 'ACTIVE')

    def test_do_rebuild_failed_retrieving_server(self):
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.server_get.return_value = None
        profile._computeclient = cc
        node_obj = mock.Mock(physical_id='FAKE_ID')

        res = profile.do_rebuild(node_obj)

        self.assertFalse(res)
        cc.server_get.assert_called_once_with('FAKE_ID')
        self.assertEqual(0, cc.server_rebuild.call_count)
        self.assertEqual(0, cc.wait_for_server.call_count)

    def test_do_rebuild_no_physical_id(self):
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = mock.Mock()

        test_server = mock.Mock()
        test_server.physical_id = None
        # Test path where server doesn't already exist
        res = profile.do_rebuild(test_server)
        self.assertFalse(res)

    def test_do_check(self):
        profile = server.ServerProfile('t', self.spec)

        cc = mock.Mock()
        cc.server_get.return_value = None
        profile._computeclient = cc

        test_server = mock.Mock(physical_id='FAKE_ID')

        res = profile.do_check(test_server)
        cc.server_get.assert_called_once_with('FAKE_ID')
        self.assertFalse(res)

        return_server = mock.Mock()
        return_server.status = 'ACTIVE'
        cc.server_get.return_value = return_server
        res = profile.do_check(test_server)
        cc.server_get.assert_called_with('FAKE_ID')
        self.assertTrue(res)

    @mock.patch.object(server.ServerProfile, 'do_rebuild')
    def test_do_recover_rebuild(self, mock_rebuild):
        profile = server.ServerProfile('t', self.spec)
        node_obj = mock.Mock(physical_id='FAKE_ID')

        res = profile.do_recover(node_obj, operation='REBUILD')

        self.assertEqual(mock_rebuild.return_value, res)
        mock_rebuild.assert_called_once_with(node_obj)

    @mock.patch.object(server.ServerProfile, 'do_rebuild')
    def test_do_recover_with_list(self, mock_rebuild):
        profile = server.ServerProfile('t', self.spec)
        node_obj = mock.Mock(physical_id='FAKE_ID')

        res = profile.do_recover(node_obj, operation=['REBUILD'])

        self.assertEqual(mock_rebuild.return_value, res)
        mock_rebuild.assert_called_once_with(node_obj)

    @mock.patch.object(profiles_base.Profile, 'do_recover')
    def test_do_recover_fallback(self, mock_base_recover):
        profile = server.ServerProfile('t', self.spec)
        node_obj = mock.Mock(physical_id='FAKE_ID')

        res = profile.do_recover(node_obj, operation='blahblah')

        self.assertEqual(mock_base_recover.return_value, res)
        mock_base_recover.assert_called_once_with(node_obj,
                                                  operation='blahblah')

    def test_handle_reboot(self):
        obj = mock.Mock(physical_id='FAKE_ID')
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.server_reboot = mock.Mock()
        cc.wait_for_server = mock.Mock()
        profile._computeclient = cc

        # do it
        res = profile.handle_reboot(obj, type='SOFT')

        self.assertTrue(res)
        cc.server_reboot.assert_called_once_with('FAKE_ID', 'SOFT')
        cc.wait_for_server.assert_called_once_with('FAKE_ID', 'ACTIVE')

    def test_handle_reboot_no_physical_id(self):
        obj = mock.Mock(physical_id=None)
        profile = server.ServerProfile('t', self.spec)

        # do it
        res = profile.handle_reboot(obj, type='SOFT')

        self.assertFalse(res)

    def test_handle_reboot_default_type(self):
        obj = mock.Mock(physical_id='FAKE_ID')
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.server_reboot = mock.Mock()
        cc.wait_for_server = mock.Mock()
        profile._computeclient = cc

        # do it
        res = profile.handle_reboot(obj)

        self.assertTrue(res)
        cc.server_reboot.assert_called_once_with('FAKE_ID', 'SOFT')
        cc.wait_for_server.assert_called_once_with('FAKE_ID', 'ACTIVE')

    def test_handle_reboot_bad_type(self):
        obj = mock.Mock(physical_id='FAKE_ID')
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = mock.Mock()

        # do it
        res = profile.handle_reboot(obj, type=['foo'])
        self.assertFalse(res)

        res = profile.handle_reboot(obj, type='foo')
        self.assertFalse(res)

    def test_handle_change_password(self):
        obj = mock.Mock(physical_id='FAKE_ID')
        profile = server.ServerProfile('t', self.spec)
        cc = mock.Mock()
        cc.server_reboot = mock.Mock()
        cc.wait_for_server = mock.Mock()
        profile._computeclient = cc

        # do it
        res = profile.handle_change_password(obj, adminPass='new_pass')

        self.assertTrue(res)
        cc.server_change_password.assert_called_once_with('FAKE_ID',
                                                          'new_pass')

    def test_handle_change_password_no_physical_id(self):
        obj = mock.Mock(physical_id=None)
        profile = server.ServerProfile('t', self.spec)

        # do it
        res = profile.handle_change_password(obj, adminPass='new_pass')

        self.assertFalse(res)

    def test_handle_change_password_no_password(self):
        obj = mock.Mock(physical_id='FAKE_ID')
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = mock.Mock()

        # do it
        res = profile.handle_change_password(obj)

        self.assertFalse(res)

    def test_handle_change_password_bad_param(self):
        obj = mock.Mock(physical_id='FAKE_ID')
        profile = server.ServerProfile('t', self.spec)
        profile._computeclient = mock.Mock()

        # do it
        res = profile.handle_change_password(obj, adminPass=['foo'])
        self.assertFalse(res)

        res = profile.handle_change_password(obj, foo='bar')
        self.assertFalse(res)
