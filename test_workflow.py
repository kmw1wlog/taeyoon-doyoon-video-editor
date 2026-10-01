import unittest
from pathlib import Path
from unittest.mock import patch

import workflow


class WorkflowTest(unittest.TestCase):
    def test_h3_request_uses_official_first_frame_shape(self):
        image = "data:image/png;base64," + "A" * 40
        with patch.object(workflow, "request_json", return_value={"task_id": "12345"}) as request:
            self.assertEqual(workflow.start_h3("temporary-key", "H3 prompt", image, 5), "12345")
        url, key, body = request.call_args.args
        self.assertEqual(url, workflow.MINIMAX_BASE + "/v2/video_generation")
        self.assertEqual(key, "temporary-key")
        self.assertEqual(body["model"], "MiniMax-H3")
        self.assertEqual(body["content"][1], {"type": "image_url", "image_url": {"url": image}, "role": "first_frame"})
        self.assertEqual(body["ratio"], "adaptive")

    def test_edit_plan_rejects_invalid_times(self):
        response = {"output": [{"content": [{"type": "output_text", "text": '{"summary":"cut","clips":[{"id":"one","start":0,"end":10}],"mutes":[]}' }]}]}
        with patch.object(workflow, "frame_data_uri", return_value="data:image/jpeg;base64,AA"), patch.object(workflow, "request_json", return_value=response):
            with self.assertRaisesRegex(ValueError, "잘못된 클립"):
                workflow.edit_plan("key", "cut", [{"id": "one", "duration": 5, "prompt": "scene"}], lambda _: Path("test.mp4"))

    def test_edit_plan_accepts_order_trim_and_mute(self):
        response = {"output": [{"content": [{"type": "output_text", "text": '{"summary":"short edit","clips":[{"id":"two","start":0.5,"end":3},{"id":"one","start":0,"end":2}],"mutes":[{"start":1,"end":1.5}]}' }]}]}
        with patch.object(workflow, "frame_data_uri", return_value="data:image/jpeg;base64,AA"), patch.object(workflow, "request_json", return_value=response) as request:
            result = workflow.edit_plan("key", "shorter", [{"id": "one", "duration": 5}, {"id": "two", "duration": 4}], lambda _: Path("test.mp4"))
        self.assertEqual([clip["id"] for clip in result["clips"]], ["two", "one"])
        self.assertEqual(request.call_args.args[2]["text"]["format"]["type"], "json_schema")


if __name__ == "__main__":
    unittest.main()
