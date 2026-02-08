"""
Admin API endpoints for managing users, teams, profiles, and viewing audit logs.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import RBACPermission, get_current_user
from src.config.logging import get_logger
from src.models.database import get_db
from src.models.pydantic_schemas import (
    AuditLogList,
    AuditLogResponse,
    DashboardStats,
    JobStatusEnum,
    SigningJobResponse,
    SigningProfileCreate,
    SigningProfileResponse,
    SigningProfileUpdate,
    TeamCreate,
    TeamResponse,
    TeamUpdate,
    UsageStats,
    UserResponse,
    UserUpdate,
)
from src.models.schemas import (
    AuditLog,
    SigningJob,
    SigningProfile,
    Team,
    User,
    UserRole,
    JobStatus,
)

logger = get_logger(__name__)

# ============================================================================
# User Management
# ============================================================================

router_users = APIRouter(prefix="/admin/users", tags=["Admin - Users"])


@router_users.get(
    "",
    response_model=list[UserResponse],
    summary="List All Users",
    dependencies=[Depends(RBACPermission("manage_users"))],
)
async def list_users(
    db: AsyncSession = Depends(get_db),
) -> list[UserResponse]:
    """List all users (admin only)."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()

    return [
        UserResponse(
            id=str(u.id),
            email=u.email,
            username=u.username,
            full_name=u.full_name,
            role=u.role.value,
            is_active=u.is_active,
            team_id=str(u.team_id) if u.team_id else None,
            created_at=u.created_at,
            last_login=u.last_login,
        )
        for u in users
    ]


@router_users.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update User",
    dependencies=[Depends(RBACPermission("manage_users"))],
)
async def update_user(
    user_id: str,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Update a user's role, status, or team assignment."""
    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id))
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if body.full_name is not None:
        user.full_name = body.full_name
    if body.role is not None:
        user.role = UserRole(body.role.value)
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.team_id is not None:
        user.team_id = uuid.UUID(body.team_id) if body.team_id else None

    await db.flush()

    return UserResponse(
        id=str(user.id),
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        role=user.role.value,
        is_active=user.is_active,
        team_id=str(user.team_id) if user.team_id else None,
        created_at=user.created_at,
        last_login=user.last_login,
    )


# ============================================================================
# Team Management
# ============================================================================

router_teams = APIRouter(prefix="/admin/teams", tags=["Admin - Teams"])


@router_teams.post(
    "",
    response_model=TeamResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Team",
    dependencies=[Depends(RBACPermission("manage_teams"))],
)
async def create_team(
    body: TeamCreate,
    db: AsyncSession = Depends(get_db),
) -> TeamResponse:
    """Create a new team."""
    # Check unique name
    result = await db.execute(select(Team).where(Team.name == body.name))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Team with this name already exists",
        )

    team = Team(name=body.name, description=body.description)
    db.add(team)
    await db.flush()

    return TeamResponse(
        id=str(team.id),
        name=team.name,
        description=team.description,
        is_active=team.is_active,
        created_at=team.created_at,
        member_count=0,
    )


@router_teams.get(
    "",
    response_model=list[TeamResponse],
    summary="List Teams",
    dependencies=[Depends(RBACPermission("manage_teams"))],
)
async def list_teams(
    db: AsyncSession = Depends(get_db),
) -> list[TeamResponse]:
    """List all teams."""
    result = await db.execute(select(Team).order_by(Team.name))
    teams = result.scalars().all()

    responses = []
    for team in teams:
        count_result = await db.execute(
            select(func.count()).where(User.team_id == team.id)
        )
        member_count = count_result.scalar() or 0

        responses.append(
            TeamResponse(
                id=str(team.id),
                name=team.name,
                description=team.description,
                is_active=team.is_active,
                created_at=team.created_at,
                member_count=member_count,
            )
        )

    return responses


@router_teams.patch(
    "/{team_id}",
    response_model=TeamResponse,
    summary="Update Team",
    dependencies=[Depends(RBACPermission("manage_teams"))],
)
async def update_team(
    team_id: str,
    body: TeamUpdate,
    db: AsyncSession = Depends(get_db),
) -> TeamResponse:
    """Update a team."""
    result = await db.execute(
        select(Team).where(Team.id == uuid.UUID(team_id))
    )
    team = result.scalar_one_or_none()

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    if body.name is not None:
        team.name = body.name
    if body.description is not None:
        team.description = body.description
    if body.is_active is not None:
        team.is_active = body.is_active

    await db.flush()

    count_result = await db.execute(
        select(func.count()).where(User.team_id == team.id)
    )
    member_count = count_result.scalar() or 0

    return TeamResponse(
        id=str(team.id),
        name=team.name,
        description=team.description,
        is_active=team.is_active,
        created_at=team.created_at,
        member_count=member_count,
    )


# ============================================================================
# Signing Profile Management
# ============================================================================

router_profiles = APIRouter(prefix="/admin/profiles", tags=["Admin - Profiles"])


@router_profiles.post(
    "",
    response_model=SigningProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Signing Profile",
    dependencies=[Depends(RBACPermission("manage_profiles"))],
)
async def create_profile(
    body: SigningProfileCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SigningProfileResponse:
    """Create a new signing profile."""
    if not current_user.team_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a team to create signing profiles",
        )

    profile = SigningProfile(
        name=body.name,
        description=body.description,
        team_id=current_user.team_id,
        certificate_name=body.certificate_name,
        algorithm=body.algorithm,
        is_default=body.is_default,
    )
    db.add(profile)
    await db.flush()

    return SigningProfileResponse(
        id=str(profile.id),
        name=profile.name,
        description=profile.description,
        team_id=str(profile.team_id),
        certificate_name=profile.certificate_name,
        algorithm=profile.algorithm,
        is_active=profile.is_active,
        is_default=profile.is_default,
        created_at=profile.created_at,
    )


@router_profiles.get(
    "",
    response_model=list[SigningProfileResponse],
    summary="List Signing Profiles",
)
async def list_profiles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SigningProfileResponse]:
    """List signing profiles."""
    query = select(SigningProfile)
    if current_user.role != UserRole.ADMIN and current_user.team_id:
        query = query.where(SigningProfile.team_id == current_user.team_id)

    result = await db.execute(query.order_by(SigningProfile.name))
    profiles = result.scalars().all()

    return [
        SigningProfileResponse(
            id=str(p.id),
            name=p.name,
            description=p.description,
            team_id=str(p.team_id),
            certificate_name=p.certificate_name,
            algorithm=p.algorithm,
            is_active=p.is_active,
            is_default=p.is_default,
            created_at=p.created_at,
        )
        for p in profiles
    ]


# ============================================================================
# Audit Logs
# ============================================================================

router_audit = APIRouter(prefix="/admin/audit", tags=["Admin - Audit"])


@router_audit.get(
    "",
    response_model=AuditLogList,
    summary="View Audit Logs",
    dependencies=[Depends(RBACPermission("view_audit"))],
)
async def list_audit_logs(
    page: int = 1,
    per_page: int = 50,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> AuditLogList:
    """View audit logs with filtering and pagination."""
    query = select(AuditLog)

    if action:
        query = query.where(AuditLog.action == action)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    query = query.order_by(AuditLog.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    logs = result.scalars().all()

    return AuditLogList(
        logs=[
            AuditLogResponse(
                id=str(log.id),
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                user_id=str(log.user_id) if log.user_id else None,
                ip_address=log.ip_address,
                details=log.details,
                status=log.status,
                created_at=log.created_at,
            )
            for log in logs
        ],
        total=total,
        page=page,
        per_page=per_page,
    )


# ============================================================================
# Dashboard Analytics
# ============================================================================

router_dashboard = APIRouter(prefix="/admin/dashboard", tags=["Admin - Dashboard"])


@router_dashboard.get(
    "/stats",
    response_model=DashboardStats,
    summary="Dashboard Statistics",
    dependencies=[Depends(RBACPermission("view_analytics"))],
)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
) -> DashboardStats:
    """Get dashboard statistics and analytics."""
    # Signing stats
    total_jobs = (
        await db.execute(select(func.count()).select_from(SigningJob))
    ).scalar() or 0

    completed_jobs = (
        await db.execute(
            select(func.count()).where(SigningJob.status == JobStatus.COMPLETED)
        )
    ).scalar() or 0

    failed_jobs = (
        await db.execute(
            select(func.count()).where(SigningJob.status == JobStatus.FAILED)
        )
    ).scalar() or 0

    # Active counts
    active_users = (
        await db.execute(
            select(func.count()).where(User.is_active == True)
        )
    ).scalar() or 0

    active_teams = (
        await db.execute(
            select(func.count()).where(Team.is_active == True)
        )
    ).scalar() or 0

    # Recent jobs
    recent_result = await db.execute(
        select(SigningJob)
        .order_by(SigningJob.created_at.desc())
        .limit(10)
    )
    recent_jobs = recent_result.scalars().all()

    return DashboardStats(
        signing_stats=UsageStats(
            total_signing_jobs=total_jobs,
            completed_jobs=completed_jobs,
            failed_jobs=failed_jobs,
            average_signing_time_ms=None,
            total_files_signed=completed_jobs,
            period="all_time",
        ),
        active_users=active_users,
        active_teams=active_teams,
        active_certificates=0,
        recent_jobs=[
            SigningJobResponse(
                job_id=str(j.id),
                status=JobStatusEnum(j.status.value),
                original_filename=j.original_filename,
                file_size=j.file_size,
                file_hash=j.file_hash,
                signature=j.signature,
                certificate_fingerprint=j.certificate_fingerprint,
                algorithm=j.algorithm,
                error_message=j.error_message,
                created_at=j.created_at,
                started_at=j.started_at,
                completed_at=j.completed_at,
            )
            for j in recent_jobs
        ],
    )
