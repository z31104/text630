import unittest

from flask import Flask, render_template_string

from routes import member


class MemberLineUserIdDisplayTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(member.member_bp)

    def test_standard_line_user_id_keeps_only_ends_visible(self):
        line_user_id = "U1234567890abcdefghijklmnopqrstuv"

        self.assertEqual(
            "U12345\u2022\u2022\u2022\u2022\u2022\u2022stuv",
            member.mask_line_user_id(line_user_id),
        )

    def test_empty_line_user_id_displays_dash(self):
        self.assertEqual("-", member.mask_line_user_id(None))
        self.assertEqual("-", member.mask_line_user_id(""))

    def test_short_nonstandard_id_does_not_reveal_entire_value(self):
        self.assertEqual(
            "H2\u2022\u2022\u2022\u2022\u2022\u202278",
            member.mask_line_user_id("H223456778"),
        )

    def test_filter_is_registered_for_templates(self):
        with self.app.app_context():
            rendered = render_template_string(
                "{{ line_user_id | mask_line_user_id }}",
                line_user_id="U1234567890abcdefghijklmnopqrstuv",
            )

        self.assertEqual(
            "U12345\u2022\u2022\u2022\u2022\u2022\u2022stuv",
            rendered,
        )


if __name__ == "__main__":
    unittest.main()
