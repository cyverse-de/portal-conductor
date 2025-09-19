"""
Tests for portal_ldap module decode and parse functions.

These tests cover the new LDAP attribute decoding functions added to portal_ldap.py:
- decode_ldap_str_attr
- decode_ldap_int_attr
- decode_ldap_list_attr
- parse_user_attributes
"""

import pytest
import portal_ldap


class TestDecodeLdapStrAttr:
    """Test decode_ldap_str_attr function."""

    def test_decode_string_attribute_bytes(self):
        """Test decoding bytes attribute value."""
        attrs = {"givenName": [b"John"]}
        result = portal_ldap.decode_ldap_str_attr(attrs, "givenName")
        assert result == "John"

    def test_decode_string_attribute_string(self):
        """Test decoding string attribute value."""
        attrs = {"givenName": ["John"]}
        result = portal_ldap.decode_ldap_str_attr(attrs, "givenName")
        assert result == "John"

    def test_decode_string_attribute_single_value(self):
        """Test decoding single (non-list) attribute value."""
        attrs = {"givenName": b"John"}
        result = portal_ldap.decode_ldap_str_attr(attrs, "givenName")
        assert result == "John"

    def test_decode_string_attribute_missing(self):
        """Test decoding missing attribute."""
        attrs = {}
        result = portal_ldap.decode_ldap_str_attr(attrs, "givenName")
        assert result is None

    def test_decode_string_attribute_empty_list(self):
        """Test decoding empty list attribute."""
        attrs = {"givenName": []}
        result = portal_ldap.decode_ldap_str_attr(attrs, "givenName")
        assert result is None

    def test_decode_string_attribute_none_value(self):
        """Test decoding None attribute value."""
        attrs = {"givenName": None}
        result = portal_ldap.decode_ldap_str_attr(attrs, "givenName")
        assert result is None

    def test_decode_string_attribute_empty_string(self):
        """Test decoding empty string attribute."""
        attrs = {"givenName": [""]}
        result = portal_ldap.decode_ldap_str_attr(attrs, "givenName")
        assert result is None

    def test_decode_string_attribute_utf8_bytes(self):
        """Test decoding UTF-8 encoded bytes."""
        attrs = {"cn": ["José García".encode('utf-8')]}
        result = portal_ldap.decode_ldap_str_attr(attrs, "cn")
        assert result == "José García"


class TestDecodeLdapIntAttr:
    """Test decode_ldap_int_attr function."""

    def test_decode_int_attribute_bytes(self):
        """Test decoding bytes integer attribute."""
        attrs = {"uidNumber": [b"12345"]}
        result = portal_ldap.decode_ldap_int_attr(attrs, "uidNumber")
        assert result == 12345

    def test_decode_int_attribute_string(self):
        """Test decoding string integer attribute."""
        attrs = {"uidNumber": ["12345"]}
        result = portal_ldap.decode_ldap_int_attr(attrs, "uidNumber")
        assert result == 12345

    def test_decode_int_attribute_single_value(self):
        """Test decoding single (non-list) integer attribute."""
        attrs = {"uidNumber": b"12345"}
        result = portal_ldap.decode_ldap_int_attr(attrs, "uidNumber")
        assert result == 12345

    def test_decode_int_attribute_missing(self):
        """Test decoding missing integer attribute."""
        attrs = {}
        result = portal_ldap.decode_ldap_int_attr(attrs, "uidNumber")
        assert result is None

    def test_decode_int_attribute_empty_list(self):
        """Test decoding empty list integer attribute."""
        attrs = {"uidNumber": []}
        result = portal_ldap.decode_ldap_int_attr(attrs, "uidNumber")
        assert result is None

    def test_decode_int_attribute_invalid_string(self):
        """Test decoding invalid integer string."""
        attrs = {"uidNumber": ["not_a_number"]}
        result = portal_ldap.decode_ldap_int_attr(attrs, "uidNumber")
        assert result is None

    def test_decode_int_attribute_float_string(self):
        """Test decoding float string as integer."""
        attrs = {"uidNumber": ["12345.67"]}
        result = portal_ldap.decode_ldap_int_attr(attrs, "uidNumber")
        assert result is None

    def test_decode_int_attribute_negative_number(self):
        """Test decoding negative integer."""
        attrs = {"shadowMin": ["-1"]}
        result = portal_ldap.decode_ldap_int_attr(attrs, "shadowMin")
        assert result == -1

    def test_decode_int_attribute_zero(self):
        """Test decoding zero."""
        attrs = {"shadowMin": ["0"]}
        result = portal_ldap.decode_ldap_int_attr(attrs, "shadowMin")
        assert result == 0


class TestDecodeLdapListAttr:
    """Test decode_ldap_list_attr function."""

    def test_decode_list_attribute_bytes(self):
        """Test decoding list of bytes attributes."""
        attrs = {"objectClass": [b"posixAccount", b"shadowAccount", b"inetOrgPerson"]}
        result = portal_ldap.decode_ldap_list_attr(attrs, "objectClass")
        assert result == ["posixAccount", "shadowAccount", "inetOrgPerson"]

    def test_decode_list_attribute_strings(self):
        """Test decoding list of string attributes."""
        attrs = {"objectClass": ["posixAccount", "shadowAccount", "inetOrgPerson"]}
        result = portal_ldap.decode_ldap_list_attr(attrs, "objectClass")
        assert result == ["posixAccount", "shadowAccount", "inetOrgPerson"]

    def test_decode_list_attribute_mixed_types(self):
        """Test decoding list with mixed bytes and strings."""
        attrs = {"objectClass": [b"posixAccount", "shadowAccount", b"inetOrgPerson"]}
        result = portal_ldap.decode_ldap_list_attr(attrs, "objectClass")
        assert result == ["posixAccount", "shadowAccount", "inetOrgPerson"]

    def test_decode_list_attribute_single_item(self):
        """Test decoding list with single item."""
        attrs = {"objectClass": [b"posixAccount"]}
        result = portal_ldap.decode_ldap_list_attr(attrs, "objectClass")
        assert result == ["posixAccount"]

    def test_decode_list_attribute_missing(self):
        """Test decoding missing list attribute."""
        attrs = {}
        result = portal_ldap.decode_ldap_list_attr(attrs, "objectClass")
        assert result is None

    def test_decode_list_attribute_empty_list(self):
        """Test decoding empty list attribute."""
        attrs = {"objectClass": []}
        result = portal_ldap.decode_ldap_list_attr(attrs, "objectClass")
        assert result is None

    def test_decode_list_attribute_utf8_bytes(self):
        """Test decoding UTF-8 encoded bytes in list."""
        attrs = {"description": ["Descripción en español".encode('utf-8'), b"English description"]}
        result = portal_ldap.decode_ldap_list_attr(attrs, "description")
        assert result == ["Descripción en español", "English description"]


class TestParseUserAttributes:
    """Test parse_user_attributes function."""

    def test_parse_user_attributes_complete(self):
        """Test parsing complete user attributes."""
        user_result = [
            ("uid=john.doe,ou=People,dc=example,dc=org", {
                "uidNumber": [b"12345"],
                "gidNumber": [b"10013"],
                "givenName": [b"John"],
                "sn": [b"Doe"],
                "cn": [b"John Doe"],
                "mail": [b"john.doe@example.org"],
                "departmentNumber": [b"Engineering"],
                "o": [b"CyVerse"],
                "title": [b"Software Engineer"],
                "homeDirectory": [b"/home/john.doe"],
                "loginShell": [b"/bin/bash"],
                "shadowLastChange": [b"19000"],
                "shadowMin": [b"1"],
                "shadowMax": [b"730"],
                "shadowWarning": [b"10"],
                "shadowInactive": [b"10"],
                "objectClass": [b"posixAccount", b"shadowAccount", b"inetOrgPerson"]
            })
        ]

        result = portal_ldap.parse_user_attributes(user_result)

        expected = {
            "uid_number": 12345,
            "gid_number": 10013,
            "given_name": "John",
            "surname": "Doe",
            "common_name": "John Doe",
            "email": "john.doe@example.org",
            "department": "Engineering",
            "organization": "CyVerse",
            "title": "Software Engineer",
            "home_directory": "/home/john.doe",
            "login_shell": "/bin/bash",
            "shadow_last_change": 19000,
            "shadow_min": 1,
            "shadow_max": 730,
            "shadow_warning": 10,
            "shadow_inactive": 10,
            "object_classes": ["posixAccount", "shadowAccount", "inetOrgPerson"]
        }

        assert result == expected

    def test_parse_user_attributes_minimal(self):
        """Test parsing minimal user attributes."""
        user_result = [
            ("uid=jane.doe,ou=People,dc=example,dc=org", {
                "uidNumber": [b"54321"],
                "gidNumber": [b"10013"],
                "givenName": [b"Jane"],
                "sn": [b"Doe"],
                "cn": [b"Jane Doe"]
            })
        ]

        result = portal_ldap.parse_user_attributes(user_result)

        expected = {
            "uid_number": 54321,
            "gid_number": 10013,
            "given_name": "Jane",
            "surname": "Doe",
            "common_name": "Jane Doe",
            "email": None,
            "department": None,
            "organization": None,
            "title": None,
            "home_directory": None,
            "login_shell": None,
            "shadow_last_change": None,
            "shadow_min": None,
            "shadow_max": None,
            "shadow_warning": None,
            "shadow_inactive": None,
            "object_classes": None
        }

        assert result == expected

    def test_parse_user_attributes_empty_result(self):
        """Test parsing empty user result."""
        user_result = []
        result = portal_ldap.parse_user_attributes(user_result)
        assert result is None

    def test_parse_user_attributes_none_result(self):
        """Test parsing None user result."""
        user_result = None
        result = portal_ldap.parse_user_attributes(user_result)
        assert result is None

    def test_parse_user_attributes_invalid_int_values(self):
        """Test parsing user attributes with invalid integer values."""
        user_result = [
            ("uid=test.user,ou=People,dc=example,dc=org", {
                "uidNumber": [b"invalid"],
                "gidNumber": [b"also_invalid"],
                "givenName": [b"Test"],
                "sn": [b"User"],
                "shadowLastChange": [b"not_a_number"]
            })
        ]

        result = portal_ldap.parse_user_attributes(user_result)

        assert result["uid_number"] is None
        assert result["gid_number"] is None
        assert result["given_name"] == "Test"
        assert result["surname"] == "User"
        assert result["shadow_last_change"] is None

    def test_parse_user_attributes_utf8_encoding(self):
        """Test parsing user attributes with UTF-8 encoded values."""
        user_result = [
            ("uid=jose.garcia,ou=People,dc=example,dc=org", {
                "uidNumber": [b"99999"],
                "gidNumber": [b"10013"],
                "givenName": ["José".encode('utf-8')],
                "sn": ["García".encode('utf-8')],
                "cn": ["José García".encode('utf-8')],
                "mail": ["josé.garcía@example.org".encode('utf-8')],
                "departmentNumber": ["Ingeniería".encode('utf-8')]
            })
        ]

        result = portal_ldap.parse_user_attributes(user_result)

        assert result["given_name"] == "José"
        assert result["surname"] == "García"
        assert result["common_name"] == "José García"
        assert result["email"] == "josé.garcía@example.org"
        assert result["department"] == "Ingeniería"

    def test_parse_user_attributes_string_values(self):
        """Test parsing user attributes with string (non-bytes) values."""
        user_result = [
            ("uid=string.user,ou=People,dc=example,dc=org", {
                "uidNumber": ["77777"],
                "gidNumber": ["10013"],
                "givenName": ["String"],
                "sn": ["User"],
                "cn": ["String User"],
                "objectClass": ["posixAccount", "shadowAccount"]
            })
        ]

        result = portal_ldap.parse_user_attributes(user_result)

        assert result["uid_number"] == 77777
        assert result["gid_number"] == 10013
        assert result["given_name"] == "String"
        assert result["surname"] == "User"
        assert result["common_name"] == "String User"
        assert result["object_classes"] == ["posixAccount", "shadowAccount"]


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_decode_functions_with_empty_dict(self):
        """Test all decode functions with empty attribute dictionary."""
        attrs = {}

        assert portal_ldap.decode_ldap_str_attr(attrs, "any_attr") is None
        assert portal_ldap.decode_ldap_int_attr(attrs, "any_attr") is None
        assert portal_ldap.decode_ldap_list_attr(attrs, "any_attr") is None

    def test_decode_functions_with_none_values(self):
        """Test decode functions with None attribute values."""
        attrs = {"test_attr": None}

        assert portal_ldap.decode_ldap_str_attr(attrs, "test_attr") is None
        assert portal_ldap.decode_ldap_int_attr(attrs, "test_attr") is None
        assert portal_ldap.decode_ldap_list_attr(attrs, "test_attr") is None

    def test_decode_int_with_very_large_number(self):
        """Test decoding very large integer."""
        attrs = {"bigNumber": [str(2**63 - 1)]}
        result = portal_ldap.decode_ldap_int_attr(attrs, "bigNumber")
        assert result == 2**63 - 1

    def test_decode_list_with_empty_strings(self):
        """Test decoding list containing empty strings."""
        attrs = {"testList": [b"", "valid", b"", "also_valid"]}
        result = portal_ldap.decode_ldap_list_attr(attrs, "testList")
        assert result == ["", "valid", "", "also_valid"]

    def test_parse_user_attributes_malformed_result(self):
        """Test parsing malformed user result structure."""
        # Missing attributes dictionary
        user_result = [("uid=test,ou=People,dc=example,dc=org",)]

        with pytest.raises(IndexError):
            portal_ldap.parse_user_attributes(user_result)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])