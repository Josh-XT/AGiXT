"""
Role and Scope Management Endpoints

This module provides API endpoints for managing custom roles and scopes
within AGiXT. Company admins can create custom roles with specific
permissions and assign them to users.
"""

from fastapi import APIRouter, Depends, Header, HTTPException
from typing import List, Optional
from MagicalAuth import (
    MagicalAuth,
    verify_api_key,
    require_scope,
    invalidate_user_scopes_cache,
)
from Models import (
    ScopeResponse,
    ScopeListResponse,
    CustomRoleCreate,
    CustomRoleUpdate,
    CustomRoleResponse,
    CustomRoleListResponse,
    UserCustomRoleAssign,
    UserCustomRoleResponse,
    UserScopesResponse,
    Detail,
)
from DB import (
    get_session,
    Scope,
    CustomRole,
    CustomRoleScope,
    UserCustomRole,
    DefaultRoleScope,
    UserCompany,
    UserRole,
    default_roles,
)
from Globals import getenv
import logging

app = APIRouter()

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


# ============================================
# Scope Endpoints
# ============================================


@app.get(
    "/v1/scopes",
    response_model=ScopeListResponse,
    summary="Get all available scopes",
    description="Returns a list of all scopes available in the system. Scopes define granular permissions.",
    tags=["Roles & Scopes"],
    dependencies=[Depends(verify_api_key)],
)
async def get_all_scopes(authorization: str = Header(None)):
    """
    Get all available scopes in the system.
    Any authenticated user can view scopes, but only admins can assign them.
    """
    with get_session() as db:
        scopes = db.query(Scope).order_by(Scope.category, Scope.name).all()

        # Get unique categories
        categories = list(set(s.category for s in scopes if s.category))
        categories.sort()

        return ScopeListResponse(
            scopes=[
                ScopeResponse(
                    id=str(s.id),
                    name=s.name,
                    resource=s.resource,
                    action=s.action,
                    description=s.description,
                    category=s.category,
                    is_system=s.is_system,
                )
                for s in scopes
            ],
            categories=categories,
        )


@app.get(
    "/v1/scopes/category/{category}",
    response_model=List[ScopeResponse],
    summary="Get scopes by category",
    description="Returns scopes filtered by category (e.g., 'Agents', 'Extensions', 'Administration').",
    tags=["Roles & Scopes"],
    dependencies=[Depends(verify_api_key)],
)
async def get_scopes_by_category(category: str, authorization: str = Header(None)):
    """Get all scopes in a specific category."""
    with get_session() as db:
        scopes = (
            db.query(Scope)
            .filter(Scope.category == category)
            .order_by(Scope.name)
            .all()
        )

        return [
            ScopeResponse(
                id=str(s.id),
                name=s.name,
                resource=s.resource,
                action=s.action,
                description=s.description,
                category=s.category,
                is_system=s.is_system,
            )
            for s in scopes
        ]


@app.get(
    "/v1/user/scopes",
    response_model=UserScopesResponse,
    summary="Get current user's scopes",
    description="Returns all scopes available to the authenticated user in their current company.",
    tags=["Roles & Scopes"],
    dependencies=[Depends(verify_api_key)],
)
async def get_my_scopes(
    company_id: Optional[str] = None,
    authorization: str = Header(None),
):
    """Get the scopes available to the current user."""
    auth = MagicalAuth(token=authorization)

    if not company_id:
        company_id = auth.company_id

    # Get user's role in this company
    with get_session() as db:
        user_company = (
            db.query(UserCompany)
            .filter(
                UserCompany.user_id == auth.user_id,
                UserCompany.company_id == company_id,
            )
            .first()
        )

        if not user_company:
            raise HTTPException(
                status_code=404,
                detail="User not found in the specified company",
            )

        role_id = user_company.role_id
        role = db.query(UserRole).filter(UserRole.id == role_id).first()
        role_name = role.friendly_name if role else "Unknown"

        # Get user's custom roles
        user_custom_roles = (
            db.query(CustomRole)
            .join(UserCustomRole, UserCustomRole.custom_role_id == CustomRole.id)
            .filter(
                UserCustomRole.user_id == auth.user_id,
                UserCustomRole.company_id == company_id,
                CustomRole.is_active == True,
            )
            .all()
        )

        custom_role_responses = []
        for cr in user_custom_roles:
            scopes = (
                db.query(Scope)
                .join(CustomRoleScope, CustomRoleScope.scope_id == Scope.id)
                .filter(CustomRoleScope.custom_role_id == cr.id)
                .all()
            )
            custom_role_responses.append(
                CustomRoleResponse(
                    id=str(cr.id),
                    company_id=str(cr.company_id),
                    name=cr.name,
                    friendly_name=cr.friendly_name,
                    description=cr.description,
                    priority=cr.priority,
                    is_active=cr.is_active,
                    scopes=[
                        ScopeResponse(
                            id=str(s.id),
                            name=s.name,
                            resource=s.resource,
                            action=s.action,
                            description=s.description,
                            category=s.category,
                            is_system=s.is_system,
                        )
                        for s in scopes
                    ],
                    created_at=cr.created_at,
                    updated_at=cr.updated_at,
                )
            )

    # Get all scopes for this user
    user_scopes = auth.get_user_scopes(company_id)

    return UserScopesResponse(
        user_id=str(auth.user_id),
        company_id=str(company_id),
        role_id=role_id,
        role_name=role_name,
        scopes=list(user_scopes),
        custom_roles=custom_role_responses,
    )


# ============================================
# Custom Role Endpoints
# ============================================


@app.get(
    "/v1/roles",
    response_model=CustomRoleListResponse,
    summary="Get custom roles for company",
    description="Returns all custom roles defined for the current company.",
    tags=["Roles & Scopes"],
    dependencies=[Depends(verify_api_key)],
)
async def get_custom_roles(
    company_id: Optional[str] = None,
    authorization: str = Header(None),
):
    """Get all custom roles for a company."""
    auth = MagicalAuth(token=authorization)
    auth.require_scope("roles:read")

    if not company_id:
        company_id = auth.company_id

    # Verify user has access to this company
    if str(company_id) not in auth.get_user_companies():
        raise HTTPException(
            status_code=403,
            detail="Access denied to the specified company",
        )

    with get_session() as db:
        custom_roles = (
            db.query(CustomRole)
            .filter(CustomRole.company_id == company_id)
            .order_by(CustomRole.priority, CustomRole.name)
            .all()
        )

        role_responses = []
        for cr in custom_roles:
            scopes = (
                db.query(Scope)
                .join(CustomRoleScope, CustomRoleScope.scope_id == Scope.id)
                .filter(CustomRoleScope.custom_role_id == cr.id)
                .all()
            )
            role_responses.append(
                CustomRoleResponse(
                    id=str(cr.id),
                    company_id=str(cr.company_id),
                    name=cr.name,
                    friendly_name=cr.friendly_name,
                    description=cr.description,
                    priority=cr.priority,
                    is_active=cr.is_active,
                    scopes=[
                        ScopeResponse(
                            id=str(s.id),
                            name=s.name,
                            resource=s.resource,
                            action=s.action,
                            description=s.description,
                            category=s.category,
                            is_system=s.is_system,
                        )
                        for s in scopes
                    ],
                    created_at=cr.created_at,
                    updated_at=cr.updated_at,
                )
            )

        return CustomRoleListResponse(roles=role_responses)


@app.post(
    "/v1/roles",
    response_model=CustomRoleResponse,
    summary="Create a custom role",
    description="Create a new custom role with specific scope assignments.",
    tags=["Roles & Scopes"],
    dependencies=[Depends(verify_api_key)],
)
async def create_custom_role(
    role: CustomRoleCreate,
    company_id: Optional[str] = None,
    authorization: str = Header(None),
):
    """Create a new custom role for a company."""
    auth = MagicalAuth(token=authorization)
    auth.require_scope("roles:write")

    if not company_id:
        company_id = auth.company_id

    # Verify user has access to this company
    if str(company_id) not in auth.get_user_companies():
        raise HTTPException(
            status_code=403,
            detail="Access denied to the specified company",
        )

    with get_session() as db:
        # Check if role name already exists in this company
        existing = (
            db.query(CustomRole)
            .filter(
                CustomRole.company_id == company_id,
                CustomRole.name == role.name,
            )
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"A role with the name '{role.name}' already exists in this company",
            )

        # Create the custom role
        new_role = CustomRole(
            company_id=company_id,
            name=role.name,
            friendly_name=role.friendly_name,
            description=role.description,
            priority=role.priority if role.priority else 100,
            is_active=True,
        )
        db.add(new_role)
        db.flush()  # Get the ID

        # Batch load all requested scopes
        scopes = db.query(Scope).filter(Scope.id.in_(role.scope_ids)).all()
        scopes_map = {str(s.id): s for s in scopes}

        # Assign scopes
        assigned_scopes = []
        for scope_id in role.scope_ids:
            scope = scopes_map.get(str(scope_id))
            if scope:
                role_scope = CustomRoleScope(
                    custom_role_id=new_role.id,
                    scope_id=scope.id,
                )
                db.add(role_scope)
                assigned_scopes.append(scope)

        db.commit()

        logging.info(
            f"Created custom role '{role.name}' in company {company_id} with {len(assigned_scopes)} scopes"
        )

        return CustomRoleResponse(
            id=str(new_role.id),
            company_id=str(new_role.company_id),
            name=new_role.name,
            friendly_name=new_role.friendly_name,
            description=new_role.description,
            priority=new_role.priority,
            is_active=new_role.is_active,
            scopes=[
                ScopeResponse(
                    id=str(s.id),
                    name=s.name,
                    resource=s.resource,
                    action=s.action,
                    description=s.description,
                    category=s.category,
                    is_system=s.is_system,
                )
                for s in assigned_scopes
            ],
            created_at=new_role.created_at,
            updated_at=new_role.updated_at,
        )


@app.get(
    "/v1/roles/{role_id}",
    response_model=CustomRoleResponse,
    summary="Get a custom role",
    description="Get details of a specific custom role.",
    tags=["Roles & Scopes"],
    dependencies=[Depends(verify_api_key)],
)
async def get_custom_role(
    role_id: str,
    authorization: str = Header(None),
):
    """Get a specific custom role by ID."""
    auth = MagicalAuth(token=authorization)
    auth.require_scope("roles:read")

    with get_session() as db:
        custom_role = db.query(CustomRole).filter(CustomRole.id == role_id).first()

        if not custom_role:
            raise HTTPException(status_code=404, detail="Custom role not found")

        # Verify user has access to this company
        if str(custom_role.company_id) not in auth.get_user_companies():
            raise HTTPException(
                status_code=403,
                detail="Access denied to the specified role",
            )

        scopes = (
            db.query(Scope)
            .join(CustomRoleScope, CustomRoleScope.scope_id == Scope.id)
            .filter(CustomRoleScope.custom_role_id == custom_role.id)
            .all()
        )

        return CustomRoleResponse(
            id=str(custom_role.id),
            company_id=str(custom_role.company_id),
            name=custom_role.name,
            friendly_name=custom_role.friendly_name,
            description=custom_role.description,
            priority=custom_role.priority,
            is_active=custom_role.is_active,
            scopes=[
                ScopeResponse(
                    id=str(s.id),
                    name=s.name,
                    resource=s.resource,
                    action=s.action,
                    description=s.description,
                    category=s.category,
                    is_system=s.is_system,
                )
                for s in scopes
            ],
            created_at=custom_role.created_at,
            updated_at=custom_role.updated_at,
        )


@app.put(
    "/v1/roles/{role_id}",
    response_model=CustomRoleResponse,
    summary="Update a custom role",
    description="Update a custom role's details and scope assignments.",
    tags=["Roles & Scopes"],
    dependencies=[Depends(verify_api_key)],
)
async def update_custom_role(
    role_id: str,
    role_update: CustomRoleUpdate,
    authorization: str = Header(None),
):
    """Update a custom role."""
    auth = MagicalAuth(token=authorization)
    auth.require_scope("roles:write")

    with get_session() as db:
        custom_role = db.query(CustomRole).filter(CustomRole.id == role_id).first()

        if not custom_role:
            raise HTTPException(status_code=404, detail="Custom role not found")

        # Verify user has access to this company
        if str(custom_role.company_id) not in auth.get_user_companies():
            raise HTTPException(
                status_code=403,
                detail="Access denied to the specified role",
            )

        # Update fields
        if role_update.friendly_name is not None:
            custom_role.friendly_name = role_update.friendly_name
        if role_update.description is not None:
            custom_role.description = role_update.description
        if role_update.priority is not None:
            custom_role.priority = role_update.priority
        if role_update.is_active is not None:
            custom_role.is_active = role_update.is_active

        # Update scopes if provided
        if role_update.scope_ids is not None:
            # Remove existing scope assignments
            db.query(CustomRoleScope).filter(
                CustomRoleScope.custom_role_id == custom_role.id
            ).delete()

            # Batch load all requested scopes
            scopes_for_assignment = (
                db.query(Scope).filter(Scope.id.in_(role_update.scope_ids)).all()
            )
            scopes_map = {str(s.id): s for s in scopes_for_assignment}

            # Add new scope assignments
            for scope_id in role_update.scope_ids:
                scope = scopes_map.get(str(scope_id))
                if scope:
                    role_scope = CustomRoleScope(
                        custom_role_id=custom_role.id,
                        scope_id=scope.id,
                    )
                    db.add(role_scope)

        db.commit()

        # Invalidate scopes cache for all users who have this role assigned
        # (Their effective scopes may have changed)
        user_assignments = (
            db.query(UserCustomRole.user_id)
            .filter(UserCustomRole.custom_role_id == custom_role.id)
            .all()
        )
        for (uid,) in user_assignments:
            invalidate_user_scopes_cache(user_id=uid, company_id=company_id)

        # Fetch updated scopes
        scopes = (
            db.query(Scope)
            .join(CustomRoleScope, CustomRoleScope.scope_id == Scope.id)
            .filter(CustomRoleScope.custom_role_id == custom_role.id)
            .all()
        )

        logging.info(f"Updated custom role '{custom_role.name}' (ID: {role_id})")

        return CustomRoleResponse(
            id=str(custom_role.id),
            company_id=str(custom_role.company_id),
            name=custom_role.name,
            friendly_name=custom_role.friendly_name,
            description=custom_role.description,
            priority=custom_role.priority,
            is_active=custom_role.is_active,
            scopes=[
                ScopeResponse(
                    id=str(s.id),
                    name=s.name,
                    resource=s.resource,
                    action=s.action,
                    description=s.description,
                    category=s.category,
                    is_system=s.is_system,
                )
                for s in scopes
            ],
            created_at=custom_role.created_at,
            updated_at=custom_role.updated_at,
        )


@app.delete(
    "/v1/roles/{role_id}",
    response_model=Detail,
    summary="Delete a custom role",
    description="Delete a custom role. Users assigned to this role will lose its permissions.",
    tags=["Roles & Scopes"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_custom_role(
    role_id: str,
    authorization: str = Header(None),
):
    """Delete a custom role."""
    auth = MagicalAuth(token=authorization)
    auth.require_scope("roles:delete")

    with get_session() as db:
        custom_role = db.query(CustomRole).filter(CustomRole.id == role_id).first()

        if not custom_role:
            raise HTTPException(status_code=404, detail="Custom role not found")

        # Verify user has access to this company
        if str(custom_role.company_id) not in auth.get_user_companies():
            raise HTTPException(
                status_code=403,
                detail="Access denied to the specified role",
            )

        role_name = custom_role.name
        company_id = str(custom_role.company_id)

        # Get all users who have this role before deleting
        user_assignments = (
            db.query(UserCustomRole.user_id)
            .filter(UserCustomRole.custom_role_id == custom_role.id)
            .all()
        )

        # Delete the role (cascade will handle scope assignments and user assignments)
        db.delete(custom_role)
        db.commit()

        # Invalidate scopes cache for all users who had this role
        for (uid,) in user_assignments:
            invalidate_user_scopes_cache(user_id=uid, company_id=company_id)

        logging.info(f"Deleted custom role '{role_name}' (ID: {role_id})")

        return Detail(detail=f"Custom role '{role_name}' deleted successfully")


# ============================================
# User Custom Role Assignment Endpoints
# ============================================


@app.post(
    "/v1/user/custom-role",
    response_model=UserCustomRoleResponse,
    summary="Assign a custom role to a user",
    description="Assign a custom role to a user in the specified company.",
    tags=["Roles & Scopes"],
    dependencies=[Depends(verify_api_key)],
)
async def assign_user_custom_role(
    assignment: UserCustomRoleAssign,
    company_id: Optional[str] = None,
    authorization: str = Header(None),
):
    """Assign a custom role to a user."""
    auth = MagicalAuth(token=authorization)
    auth.require_scope("users:roles")

    if not company_id:
        company_id = auth.company_id

    # Verify user has access to this company
    if str(company_id) not in auth.get_user_companies():
        raise HTTPException(
            status_code=403,
            detail="Access denied to the specified company",
        )

    with get_session() as db:
        # Verify the custom role exists and belongs to this company
        custom_role = (
            db.query(CustomRole)
            .filter(
                CustomRole.id == assignment.custom_role_id,
                CustomRole.company_id == company_id,
            )
            .first()
        )

        if not custom_role:
            raise HTTPException(
                status_code=404,
                detail="Custom role not found in this company",
            )

        # Verify the target user is in this company
        user_company = (
            db.query(UserCompany)
            .filter(
                UserCompany.user_id == assignment.user_id,
                UserCompany.company_id == company_id,
            )
            .first()
        )

        if not user_company:
            raise HTTPException(
                status_code=404,
                detail="User not found in this company",
            )

        # Check if assignment already exists
        existing = (
            db.query(UserCustomRole)
            .filter(
                UserCustomRole.user_id == assignment.user_id,
                UserCustomRole.company_id == company_id,
                UserCustomRole.custom_role_id == assignment.custom_role_id,
            )
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=409,
                detail="User already has this custom role assigned",
            )

        # Create the assignment
        user_custom_role = UserCustomRole(
            user_id=assignment.user_id,
            company_id=company_id,
            custom_role_id=assignment.custom_role_id,
            assigned_by=auth.user_id,
        )
        db.add(user_custom_role)
        db.commit()

        # Invalidate user scopes cache since their permissions changed
        invalidate_user_scopes_cache(user_id=assignment.user_id, company_id=company_id)

        # Fetch scopes for response
        scopes = (
            db.query(Scope)
            .join(CustomRoleScope, CustomRoleScope.scope_id == Scope.id)
            .filter(CustomRoleScope.custom_role_id == custom_role.id)
            .all()
        )

        logging.info(
            f"Assigned custom role '{custom_role.name}' to user {assignment.user_id} in company {company_id}"
        )

        return UserCustomRoleResponse(
            id=str(user_custom_role.id),
            user_id=str(user_custom_role.user_id),
            company_id=str(user_custom_role.company_id),
            custom_role=CustomRoleResponse(
                id=str(custom_role.id),
                company_id=str(custom_role.company_id),
                name=custom_role.name,
                friendly_name=custom_role.friendly_name,
                description=custom_role.description,
                priority=custom_role.priority,
                is_active=custom_role.is_active,
                scopes=[
                    ScopeResponse(
                        id=str(s.id),
                        name=s.name,
                        resource=s.resource,
                        action=s.action,
                        description=s.description,
                        category=s.category,
                        is_system=s.is_system,
                    )
                    for s in scopes
                ],
                created_at=custom_role.created_at,
                updated_at=custom_role.updated_at,
            ),
            assigned_at=user_custom_role.assigned_at,
        )


@app.delete(
    "/v1/user/{user_id}/custom-role/{custom_role_id}",
    response_model=Detail,
    summary="Remove a custom role from a user",
    description="Remove a custom role assignment from a user.",
    tags=["Roles & Scopes"],
    dependencies=[Depends(verify_api_key)],
)
async def remove_user_custom_role(
    user_id: str,
    custom_role_id: str,
    company_id: Optional[str] = None,
    authorization: str = Header(None),
):
    """Remove a custom role from a user."""
    auth = MagicalAuth(token=authorization)
    auth.require_scope("users:roles")

    if not company_id:
        company_id = auth.company_id

    # Verify user has access to this company
    if str(company_id) not in auth.get_user_companies():
        raise HTTPException(
            status_code=403,
            detail="Access denied to the specified company",
        )

    with get_session() as db:
        # Find the assignment
        assignment = (
            db.query(UserCustomRole)
            .filter(
                UserCustomRole.user_id == user_id,
                UserCustomRole.company_id == company_id,
                UserCustomRole.custom_role_id == custom_role_id,
            )
            .first()
        )

        if not assignment:
            raise HTTPException(
                status_code=404,
                detail="Custom role assignment not found",
            )

        db.delete(assignment)
        db.commit()

        # Invalidate user scopes cache since their permissions changed
        invalidate_user_scopes_cache(user_id=user_id, company_id=company_id)

        logging.info(
            f"Removed custom role {custom_role_id} from user {user_id} in company {company_id}"
        )

        return Detail(detail="Custom role removed from user successfully")


@app.get(
    "/v1/user/{user_id}/custom-roles",
    response_model=List[UserCustomRoleResponse],
    summary="Get user's custom roles",
    description="Get all custom roles assigned to a user in a company.",
    tags=["Roles & Scopes"],
    dependencies=[Depends(verify_api_key)],
)
async def get_user_custom_roles(
    user_id: str,
    company_id: Optional[str] = None,
    authorization: str = Header(None),
):
    """Get all custom roles assigned to a user."""
    auth = MagicalAuth(token=authorization)
    auth.require_scope("users:read")

    if not company_id:
        company_id = auth.company_id

    # Verify user has access to this company
    if str(company_id) not in auth.get_user_companies():
        raise HTTPException(
            status_code=403,
            detail="Access denied to the specified company",
        )

    with get_session() as db:
        assignments = (
            db.query(UserCustomRole)
            .filter(
                UserCustomRole.user_id == user_id,
                UserCustomRole.company_id == company_id,
            )
            .all()
        )

        responses = []
        for assignment in assignments:
            custom_role = (
                db.query(CustomRole)
                .filter(CustomRole.id == assignment.custom_role_id)
                .first()
            )

            if not custom_role:
                continue

            scopes = (
                db.query(Scope)
                .join(CustomRoleScope, CustomRoleScope.scope_id == Scope.id)
                .filter(CustomRoleScope.custom_role_id == custom_role.id)
                .all()
            )

            responses.append(
                UserCustomRoleResponse(
                    id=str(assignment.id),
                    user_id=str(assignment.user_id),
                    company_id=str(assignment.company_id),
                    custom_role=CustomRoleResponse(
                        id=str(custom_role.id),
                        company_id=str(custom_role.company_id),
                        name=custom_role.name,
                        friendly_name=custom_role.friendly_name,
                        description=custom_role.description,
                        priority=custom_role.priority,
                        is_active=custom_role.is_active,
                        scopes=[
                            ScopeResponse(
                                id=str(s.id),
                                name=s.name,
                                resource=s.resource,
                                action=s.action,
                                description=s.description,
                                category=s.category,
                                is_system=s.is_system,
                            )
                            for s in scopes
                        ],
                        created_at=custom_role.created_at,
                        updated_at=custom_role.updated_at,
                    ),
                    assigned_at=assignment.assigned_at,
                )
            )

        return responses


# ============================================
# Default Role Scope Endpoints
# ============================================


@app.get(
    "/v1/default-roles",
    summary="Get default system roles with their scopes",
    description="Returns the default system roles and their assigned scopes.",
    tags=["Roles & Scopes"],
    dependencies=[Depends(verify_api_key)],
)
async def get_default_roles_with_scopes(authorization: str = Header(None)):
    """Get all default system roles with their scope assignments."""
    with get_session() as db:
        result = []

        # Sort default_roles by display_order for consistent UI ordering
        sorted_roles = sorted(default_roles, key=lambda r: r.get("display_order", 100))

        for role_data in sorted_roles:
            role_id = role_data["id"]

            # Get scopes for this role
            scopes = (
                db.query(Scope)
                .join(DefaultRoleScope, DefaultRoleScope.scope_id == Scope.id)
                .filter(DefaultRoleScope.role_id == role_id)
                .all()
            )

            result.append(
                {
                    "id": role_id,
                    "name": role_data["name"],
                    "friendly_name": role_data["friendly_name"],
                    "display_order": role_data.get("display_order", 100),
                    "scopes": [
                        {
                            "id": str(s.id),
                            "name": s.name,
                            "resource": s.resource,
                            "action": s.action,
                            "description": s.description,
                            "category": s.category,
                        }
                        for s in scopes
                    ],
                }
            )

        return {"roles": result}


@app.put(
    "/v1/default-roles/{role_id}/scopes",
    summary="Update default role scopes (Super Admin only)",
    description="Update the scopes assigned to a default system role. Super Admin access required.",
    tags=["Roles & Scopes"],
    dependencies=[Depends(verify_api_key)],
)
async def update_default_role_scopes(
    role_id: int,
    scope_ids: List[str],
    authorization: str = Header(None),
):
    """
    Update the scopes assigned to a default system role.
    Only super admins can modify default role scopes.

    Args:
        role_id: The ID of the default role (0-5)
        scope_ids: List of scope IDs to assign to the role
    """
    auth = MagicalAuth(token=authorization)

    # Only super admins can modify default roles
    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Only super admins can modify default role scopes",
        )

    # Validate role_id
    if role_id < 0 or role_id > 5:
        raise HTTPException(
            status_code=400,
            detail="Invalid role_id. Must be between 0 and 5.",
        )

    # Super admin role (0) cannot have its scopes modified - it always has "*"
    if role_id == 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot modify super admin role scopes. Super admin always has all permissions.",
        )

    with get_session() as db:
        # Validate all scope_ids exist
        valid_scopes = db.query(Scope).filter(Scope.id.in_(scope_ids)).all()
        valid_scope_ids = {str(s.id) for s in valid_scopes}

        invalid_ids = set(scope_ids) - valid_scope_ids
        if invalid_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid scope IDs: {', '.join(invalid_ids)}",
            )

        # Remove all existing scope assignments for this role
        db.query(DefaultRoleScope).filter(DefaultRoleScope.role_id == role_id).delete()

        # Add new scope assignments
        for scope in valid_scopes:
            role_scope = DefaultRoleScope(
                role_id=role_id,
                scope_id=scope.id,
            )
            db.add(role_scope)

        db.commit()

        # Return the updated role with scopes
        role_data = next((r for r in default_roles if r["id"] == role_id), None)

        return {
            "id": role_id,
            "name": role_data["name"] if role_data else "Unknown",
            "friendly_name": role_data["friendly_name"] if role_data else "Unknown",
            "scopes": [
                {
                    "id": str(s.id),
                    "name": s.name,
                    "resource": s.resource,
                    "action": s.action,
                    "description": s.description,
                    "category": s.category,
                }
                for s in valid_scopes
            ],
            "message": f"Successfully updated {len(valid_scopes)} scopes for role {role_id}",
        }
