import pytest
from middlewared.utils import filter_list


DATA = [
    {
        'foo': 'foo1',
        'number': 1,
        'list': [1],
    },
    {
        'foo': 'foo2',
        'number': 2,
        'list': [2],
    },
    {
        'foo': '_foo_',
        'number': 3,
        'list': [3],
    },
]

DATA_WITH_NULL = [
    {
        'foo': 'foo1',
        'number': 1,
        'list': [1],
    },
    {
        'foo': 'foo2',
        'number': 2,
        'list': [2],
    },
    {
        'foo': '_foo_',
        'number': 3,
        'list': [3],
    },
    {
        'foo': None,
        'number': 4,
        'list': [4],
    },
]

DATA_WITH_CASE = [
    {
        'foo': 'foo',
        'number': 1,
        'list': [1],
    },
    {
        'foo': 'Foo',
        'number': 2,
        'list': [2],
    },
    {
        'foo': 'foO_',
        'number': 3,
        'list': [3],
    },
    {
        'foo': 'bar',
        'number': 3,
        'list': [3],
    },
]

DATA_SELECT_COMPLEX = [
    {
        'foo': 'foo',
        'number': 1,
        'foobar': {'stuff': {'more_stuff': 1}},
        'foo.bar': 42,
        'list': [1],
    },
    {
        'foo': 'Foo',
        'number': 2,
        'foobar': {'stuff': {'more_stuff': 2}},
        'foo.bar': 43,
        'list': [2],
    },
    {
        'foo': 'foO_',
        'number': 3,
        'foobar': {'stuff': {'more_stuff': 2}},
        'foo.bar': 44,
        'list': [3],
    },
    {
        'foo': 'bar',
        'number': 4,
        'foobar': {'stuff': {'more_stuff': 4}},
        'foo.bar': 45,
        'list': [4],
    },
]

COMPLEX_DATA = [
    {
        "timestamp": "2022-11-10T07:40:17.397502-0800",
        "type": "Authentication",
        "Authentication": {
            "version": {
                "major": 1,
                "minor": 2
            },
            "eventId": 4625,
            "logonId": "0",
            "logonType": 3,
            "status": "NT_STATUS_NO_SUCH_USER",
            "localAddress": "ipv4:192.168.0.200:445",
            "remoteAddress": "ipv4:192.168.0.151:50559",
            "serviceDescription": "SMB2",
            "authDescription": None,
            "clientDomain": "MicrosoftAccount",
            "clientAccount": "awalker325@outlook.com",
            "workstation": "WALKSURF",
            "becameAccount": None,
            "becameDomain": None,
            "becameSid": None,
            "mappedAccount": "awalker325@outlook.com",
            "mappedDomain": "MicrosoftAccount",
            "netlogonComputer": None,
            "netlogonTrustAccount": None,
            "netlogonNegotiateFlags": "0x00000000",
            "netlogonSecureChannelType": 0,
            "netlogonTrustAccountSid": None,
            "passwordType": "NTLMv2",
            "duration": 6298
        },
        "timestamp_tval": {
            "tv_sec": 1668094817,
            "tv_usec": 397502
        }
    },
    {
        "timestamp": "2023-01-24T12:37:39.522594-0800",
        "type": "Authentication",
        "Authentication": {
            "version": {
                "major": 1,
                "minor": 2
            },
            "eventId": 4624,
            "logonId": "c1b1a262c42babb6",
            "logonType": 8,
            "status": "NT_STATUS_OK",
            "localAddress": "unix:",
            "remoteAddress": "unix:",
            "serviceDescription": "winbind",
            "authDescription": "PAM_AUTH, PAM_WINBIND[sshd], 133191",
            "clientDomain": "BILLY",
            "clientAccount": "joiner",
            "workstation": None,
            "becameAccount": "joiner",
            "becameDomain": "BILLY",
            "becameSid": "S-1-5-21-1002530428-2020721000-3540273080-1103",
            "mappedAccount": None,
            "mappedDomain": None,
            "netlogonComputer": None,
            "netlogonTrustAccount": None,
            "netlogonNegotiateFlags": "0x00000000",
            "netlogonSecureChannelType": 0,
            "netlogonTrustAccountSid": None,
            "passwordType": "Plaintext",
            "duration": 23554
        },
        "timestamp_tval": {
            "tv_sec": 1674592659,
            "tv_usec": 522594
        }
    }
]


def test__filter_list_equal():
    assert len(filter_list(DATA, [['foo', '=', 'foo1']])) == 1


def test__filter_list_starts():
    assert len(filter_list(DATA, [['foo', '^', 'foo']])) == 2


def test__filter_list_ends():
    assert len(filter_list(DATA, [['foo', '$', '_']])) == 1


def test__filter_list_regex_begins():
    assert len(filter_list(DATA, [['foo', '~', '^foo']])) == 2


def test__filter_list_regex_contains():
    assert len(filter_list(DATA, [['foo', '~', '.*foo.*']])) == 3


def test__filter_list_gt():
    assert len(filter_list(DATA, [['number', '>', 1]])) == 2


def test__filter_list_gte():
    assert len(filter_list(DATA, [['number', '>=', 1]])) == 3


def test__filter_list_lt():
    assert len(filter_list(DATA, [['number', '<', 3]])) == 2


def test__filter_list_lte():
    assert len(filter_list(DATA, [['number', '<=', 3]])) == 3


def test__filter_list_in():
    assert len(filter_list(DATA, [['number', 'in', [1, 3]]])) == 2


def test__filter_list_nin():
    assert len(filter_list(DATA, [['number', 'nin', [1, 3]]])) == 1


def test__filter_list_rin():
    assert len(filter_list(DATA, [['list', 'rin', 1]])) == 1


def test__filter_list_rnin():
    assert len(filter_list(DATA, [['list', 'rnin', 1]])) == 2


def test__filter_list_OR_eq1():
    assert len(filter_list(DATA, [['OR', [
        ['number', '=', 1],
        ['number', '=', 200],
    ]]])) == 1


def test__filter_list_OR_eq2():
    assert len(filter_list(DATA, [['OR', [
        ['number', '=', 1],
        ['number', '=', 2],
    ]]])) == 2


def test__filter_list_OR_eq3():
    assert len(filter_list(DATA, [['OR', [
        [['number', '=', 1], ['foo', '=', 'foo1']],
        ['number', '=', 2],
    ]]])) == 2

    assert len(filter_list(DATA, [['OR', [
        [['number', '=', 1], ['foo', '=', 'foo2']],
        ['number', '=', 2],
    ]]])) == 1


def test__filter_list_OR_nesting():
    assert len(filter_list(DATA, [['OR', [
        ['OR', [['number', '=', 1], ['foo', '=', 'canary']]],
        ['number', '=', 2],
    ]]])) == 2

    assert len(filter_list(DATA, [['OR', [
        ['OR', [['number', '=', 'canary'], ['foo', '=', 'canary']]],
        ['number', '=', 2],
    ]]])) == 1

    assert len(filter_list(DATA, [['OR', [
        ['OR', [
            ['OR', [
                ['number', '=', 1],
                ['number', '=', 'canary'],
            ]],
            ['foo', '=', 'canary']
        ]],
        ['number', '=', 2],
    ]]])) == 2

    with pytest.raises(ValueError) as ve:
        filter_list(DATA, [['OR', [
            ['OR', [
                ['OR', [
                    ['OR', [
                        ['number', '=', 1],
                        ['number', '=', 'canary'],
                    ]],
                    ['number', '=', 1],
                    ['number', '=', 'canary'],
                ]],
                ['foo', '=', 'canary']
            ]],
            ['number', '=', 2],
        ]]])
        assert 'query-filters max recursion depth exceeded' in str(ve)


def test__filter_list_nested_dict():
    assert len(filter_list(COMPLEX_DATA, [['Authentication.status', '=', 'NT_STATUS_OK']])) == 1


def test__filter_list_option_get():
    assert isinstance(filter_list(DATA, [], {'get': True}), dict)


def test__filter_list_option_get_and_order_by():
    assert filter_list(DATA, [], {'get': True, 'order_by': ['-number']})['foo'] == '_foo_'


def test__filter_list_option_order_by():
    for idx, entry in enumerate(filter_list(DATA, [], {'order_by': ['number']})):
        assert entry['number'] == idx + 1


def test__filter_list_option_order_by_reverse():
    for idx, entry in enumerate(filter_list(DATA, [], {'order_by': ['-number']})):
        assert entry['number'] == 3 - idx


def test__filter_list_option_select():
    for entry in filter_list(DATA, [], {'select': ['foo']}):
        assert list(entry.keys()) == ['foo']


def test__filter_list_option_nulls_first():
    assert filter_list(DATA_WITH_NULL, [], {'order_by': ['nulls_first:foo']})[0]['foo'] is None


def test__filter_list_option_nulls_last():
    assert filter_list(DATA_WITH_NULL, [], {'order_by': ['nulls_last:foo']})[-1]['foo'] is None


def test__filter_list_option_casefold_equals():
    assert len(filter_list(DATA, [['foo', 'C=', 'Foo1']])) == 1


def test__filter_list_option_casefold_starts():
    assert len(filter_list(DATA_WITH_CASE, [['foo', 'C^', 'F']])) == 3


def test__filter_list_option_casefold_does_not_start():
    assert len(filter_list(DATA_WITH_CASE, [['foo', 'C!^', 'F']])) == 1


def test__filter_list_option_casefold_ends():
    assert len(filter_list(DATA_WITH_CASE, [['foo', 'C$', 'foo']])) == 2


def test__filter_list_option_casefold_does_not_end():
    assert len(filter_list(DATA_WITH_CASE, [['foo', 'C!$', 'O']])) == 2


def test__filter_list_option_casefold_in():
    assert len(filter_list(DATA_WITH_CASE, [['foo', 'Cin', 'foo']])) == 2


def test__filter_list_option_casefold_rin():
    assert len(filter_list(DATA_WITH_CASE, [['foo', 'Crin', 'foo']])) == 3


def test__filter_list_option_casefold_nin():
    assert len(filter_list(DATA_WITH_CASE, [['foo', 'Cnin', 'foo']])) == 2


def test__filter_list_option_casefold_rnin():
    assert len(filter_list(DATA_WITH_CASE, [['foo', 'Crnin', 'foo']])) == 1


def test__filter_list_option_casefold_complex_data():
    assert len(filter_list(COMPLEX_DATA, [['Authentication.clientAccount', 'C=', 'JOINER']])) == 1


def test__filter_list_nested_select():
    data = filter_list(
        DATA_SELECT_COMPLEX,
        [['foobar.stuff.more_stuff', '=', 4]],
        {'select': ['foobar.stuff.more_stuff']}
    )
    assert len(data) == 1
    entry = data[0]
    assert 'foobar' in entry
    assert 'stuff' in entry['foobar']
    assert 'more_stuff' in entry['foobar']['stuff']
    assert entry['foobar']['stuff']['more_stuff'] == 4


def test__filter_list_nested_select_escape():
    data = filter_list(DATA_SELECT_COMPLEX, [['foobar.stuff.more_stuff', '=', 4]], {'select': ['foo\\.bar']})
    assert len(data) == 1
    entry = data[0]
    assert 'foo.bar' in entry
    assert entry['foo.bar'] == 45


def test__filter_list_complex_data_nested_select():
    data = filter_list(
        COMPLEX_DATA,
        [],
        {'select': ['Authentication.status', 'Authentication.localAddress', 'Authentication.clientAccount']}
    )
    assert len(data) != 0
    assert 'Authentication' in data[0]
    auth = data[0]['Authentication']
    assert len(auth.keys()) == 3
    assert 'status' in auth
    assert 'localAddress' in auth
    assert 'clientAccount' in auth


def test__filter_list_select_as():
    data = filter_list(
        DATA_SELECT_COMPLEX,
        [['foobar.stuff.more_stuff', '=', 4]],
        {'select': [['foobar.stuff.more_stuff', 'data']]}
    )
    assert len(data) == 1
    entry = data[0]
    assert len(entry.keys()) == 1
    assert 'data' in entry
    assert entry['data'] == 4


def test__filter_list_select_null():
    data = filter_list(DATA_WITH_NULL, [['number', '=', 4]], {'select': ['foo'], 'get': True})
    assert len(data) == 1
    assert 'foo' in data
    assert data['foo'] is None


def test__filter_list_select_as_validation():
    with pytest.raises(ValueError) as ve:
        # too few items in the select list
        filter_list(DATA_SELECT_COMPLEX, [], {'select': [['foobar.stuff.more_stuff']]})
        assert 'select as list may only contain two parameters' in str(ve)

    with pytest.raises(ValueError) as ve:
        # too many items in the select list
        filter_list(DATA_SELECT_COMPLEX, [], {'select': [['foobar.stuff.more_stuff', 'cat', 'dog']]})
        assert 'select as list may only contain two parameters' in str(ve)

    with pytest.raises(ValueError) as ve:
        # wrong type in select
        filter_list(DATA_SELECT_COMPLEX, [], {'select': [[1, 'cat']]})
        assert 'first item must be a string' in str(ve)
