import xml.etree.ElementTree as ET
import os
from pydantic import BaseModel
from typing import List, Optional

class TestCaseFailure(BaseModel):
    name: str
    message: str
    stack_trace: str
    file: Optional[str] = None
    line: Optional[str] = None

class TestReport(BaseModel):
    total: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    failed_cases: List[TestCaseFailure] = []
    
    @property
    def is_pass(self) -> bool:
        return self.failures == 0 and self.errors == 0

class TestParser:
    @staticmethod
    def parse_junit_xml(file_path: str) -> TestReport:
        if not os.path.exists(file_path):
            return TestReport()
            
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            # JUnit XML format usually has <testsuites> -> <testsuite> -> <testcase>
            # Or just <testsuite> at root.
            
            report = TestReport()
            
            # Aggregate stats
            for suite in root.iter("testsuite"):
                report.total += int(suite.attrib.get("tests", 0))
                report.failures += int(suite.attrib.get("failures", 0))
                report.errors += int(suite.attrib.get("errors", 0))
                report.skipped += int(suite.attrib.get("skipped", 0))

            # If no testsuites tag, try root attribs
            if report.total == 0 and root.tag == "testsuite":
                report.total = int(root.attrib.get("tests", 0))
                report.failures = int(root.attrib.get("failures", 0))
                report.errors = int(root.attrib.get("errors", 0))
                report.skipped = int(root.attrib.get("skipped", 0))

            # Extract failures
            for testcase in root.iter("testcase"):
                failure = testcase.find("failure")
                error = testcase.find("error")
                
                node = failure if failure is not None else error
                if node is not None:
                    name = testcase.attrib.get("name", "unknown")
                    classname = testcase.attrib.get("classname", "")
                    file_path = testcase.attrib.get("file")
                    line = testcase.attrib.get("line")
                    
                    full_name = f"{classname}::{name}" if classname else name
                    msg = node.attrib.get("message", "No message")
                    text = node.text or ""
                    
                    report.failed_cases.append(TestCaseFailure(
                        name=full_name,
                        message=msg,
                        stack_trace=text.strip(),
                        file=file_path,
                        line=line
                    ))
                    
            return report
            
        except Exception as e:
            # Fallback
            return TestReport(failures=1, failed_cases=[TestCaseFailure(name="ParserError", message=f"Failed to parse XML: {e}", stack_trace="")])
