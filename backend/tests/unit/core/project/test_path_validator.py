import os
import pytest
from unittest.mock import patch, MagicMock
from app.core.project.path_validator import validate_project_path
from app.models.codebase import Repository

def make_fake_session_scope(active_repos):
    class FakeSession:
        async def execute(self, stmt):
            class FakeResult:
                def scalars(self):
                    return self
                def all(self):
                    return active_repos
            return FakeResult()
            
    class FakeScope:
        async def __aenter__(self):
            return FakeSession()
        async def __aexit__(self, exc_type, exc, tb):
            return False
            
    return FakeScope

@pytest.mark.asyncio
async def test_valid_project_path():
    workspace = "/tmp/ws"
    candidate = "/tmp/ws/project-1"
    
    with patch("app.core.project.path_validator.session_scope", make_fake_session_scope([])):
        # Should not raise any exception
        await validate_project_path(candidate, workspace)

@pytest.mark.asyncio
async def test_validate_path_outside_workspace():
    workspace = "/tmp/ws"
    candidate = "/tmp/other/project-1"
    
    with patch("app.core.project.path_validator.session_scope", make_fake_session_scope([])):
        with pytest.raises(ValueError, match="Project path must reside within the workspace root"):
            await validate_project_path(candidate, workspace)

@pytest.mark.asyncio
async def test_validate_path_is_workspace_root():
    workspace = "/tmp/ws"
    candidate = "/tmp/ws"
    
    with patch("app.core.project.path_validator.session_scope", make_fake_session_scope([])):
        with pytest.raises(ValueError, match="Cannot register the workspace root itself as a project"):
            await validate_project_path(candidate, workspace)

@pytest.mark.asyncio
async def test_validate_path_hidden_folders():
    workspace = "/tmp/ws"
    candidate_dot = "/tmp/ws/.hidden"
    candidate_tilde = "/tmp/ws/~backup"
    candidate_under = "/tmp/ws/_system"
    
    with patch("app.core.project.path_validator.session_scope", make_fake_session_scope([])):
        with pytest.raises(ValueError, match="Project path cannot contain system or hidden folder names"):
            await validate_project_path(candidate_dot, workspace)
            
        with pytest.raises(ValueError, match="Project path cannot contain system or hidden folder names"):
            await validate_project_path(candidate_tilde, workspace)
            
        with pytest.raises(ValueError, match="Project path cannot contain system or hidden folder names"):
            await validate_project_path(candidate_under, workspace)

@pytest.mark.asyncio
async def test_validate_path_ignored_name():
    workspace = "/tmp/ws"
    candidate = "/tmp/ws/node_modules"
    
    with patch("app.core.project.path_validator.session_scope", make_fake_session_scope([])):
        with pytest.raises(ValueError, match="Project path matches excluded directory names"):
            await validate_project_path(candidate, workspace)

@pytest.mark.asyncio
async def test_validate_path_overlapping_exact():
    workspace = "/tmp/ws"
    candidate = "/tmp/ws/proj-a"
    
    repo = Repository(
        name="proj-a",
        local_path="/tmp/ws/proj-a",
        sync_status="SYNCED"
    )
    
    with patch("app.core.project.path_validator.session_scope", make_fake_session_scope([repo])):
        with pytest.raises(ValueError, match="A project is already registered at this path"):
            await validate_project_path(candidate, workspace)

@pytest.mark.asyncio
async def test_validate_path_overlapping_sub():
    workspace = "/tmp/ws"
    candidate = "/tmp/ws/proj-a/subdir"
    
    repo = Repository(
        name="proj-a",
        local_path="/tmp/ws/proj-a",
        sync_status="SYNCED"
    )
    
    with patch("app.core.project.path_validator.session_scope", make_fake_session_scope([repo])):
        with pytest.raises(ValueError, match="Path cannot be inside another project"):
            await validate_project_path(candidate, workspace)

@pytest.mark.asyncio
async def test_validate_path_overlapping_parent():
    workspace = "/tmp/ws"
    candidate = "/tmp/ws/proj-a"
    
    repo = Repository(
        name="subproject",
        local_path="/tmp/ws/proj-a/subdir",
        sync_status="SYNCED"
    )
    
    with patch("app.core.project.path_validator.session_scope", make_fake_session_scope([repo])):
        with pytest.raises(ValueError, match="Path cannot contain another project"):
            await validate_project_path(candidate, workspace)
