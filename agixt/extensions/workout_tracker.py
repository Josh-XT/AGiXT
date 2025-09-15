"""
Workout Tracker Extension for AGiXT
This extension provides workout tracking capabilities with database persistence.
"""

import json
import logging
import warnings
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Float,
    DateTime,
    ForeignKey,
    Boolean,
    Date,
    UniqueConstraint,
    func,
    and_,
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.exc import SAWarning
from Extensions import Extensions
from DB import get_session, ExtensionDatabaseMixin, Base  # Import Base from DB.py

# Suppress the specific SQLAlchemy warning about duplicate class registration
warnings.filterwarnings(
    "ignore",
    message=".*This declarative base already contains a class with the same class name.*",
    category=SAWarning,
)


# Database Models for Workout Tracker
class WorkoutTrackerDailyGoal(Base):
    """Model for daily exercise goals"""

    __tablename__ = "workout_tracker_daily_goals"
    __table_args__ = (
        UniqueConstraint("user_id", "exercise_name", name="unique_user_exercise_goal"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    exercise_name = Column(String(255), nullable=False)
    target_reps = Column(Integer, nullable=False)
    target_sets = Column(Integer, default=1)
    target_weight = Column(Float, default=0)  # in kg or lbs
    target_duration = Column(Integer, default=0)  # in seconds
    muscle_group = Column(String(100))
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "exercise_name": self.exercise_name,
            "target_reps": self.target_reps,
            "target_sets": self.target_sets,
            "target_weight": self.target_weight,
            "target_duration": self.target_duration,
            "muscle_group": self.muscle_group,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class WorkoutTrackerDailyCompletion(Base):
    """Model for tracking daily exercise completions"""

    __tablename__ = "workout_tracker_daily_completions"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "exercise_name",
            "completion_date",
            name="unique_daily_completion",
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    exercise_name = Column(String(255), nullable=False)
    completion_date = Column(Date, nullable=False, default=date.today)
    completed_reps = Column(Integer, nullable=False)
    completed_sets = Column(Integer, default=1)
    completed_weight = Column(Float, default=0)  # in kg or lbs
    completed_duration = Column(Integer, default=0)  # in seconds
    notes = Column(Text)
    completed_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "exercise_name": self.exercise_name,
            "completion_date": (
                self.completion_date.isoformat() if self.completion_date else None
            ),
            "completed_reps": self.completed_reps,
            "completed_sets": self.completed_sets,
            "completed_weight": self.completed_weight,
            "completed_duration": self.completed_duration,
            "notes": self.notes,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
        }


class workout_tracker(Extensions, ExtensionDatabaseMixin):
    """Workout Tracker Extension with database support"""

    CATEGORY = "Health & Fitness"

    # Register extension models for automatic table creation
    extension_models = [WorkoutTrackerDailyGoal, WorkoutTrackerDailyCompletion]

    def __init__(self, **kwargs):
        self.AGENT = kwargs
        self.user_id = kwargs.get("user_id", kwargs.get("user", "default"))
        self.ApiClient = kwargs.get("ApiClient", None)

        # Register models with ExtensionDatabaseMixin
        self.register_models()

        # Define available commands
        self.commands = {
            # Daily Goal Management
            "Set Daily Goal": self.set_daily_goal,
            "Get Daily Goals": self.get_daily_goals,
            "Update Daily Goal": self.update_daily_goal,
            "Delete Daily Goal": self.delete_daily_goal,
            # Daily Completion Management
            "Mark Exercise Complete": self.mark_exercise_complete,
            "Get Daily Progress": self.get_daily_progress,
            "Get Weekly Progress": self.get_weekly_progress,
            "Get Monthly Progress": self.get_monthly_progress,
        }

    # Daily Goal Management Commands

    def set_daily_goal(
        self,
        exercise_name: str,
        target_reps: int,
        target_sets: int = 1,
        target_weight: float = 0,
        target_duration: int = 0,
        muscle_group: str = "",
    ) -> str:
        """Set a daily goal for an exercise"""
        session = get_session()
        try:
            # Check if goal already exists
            existing_goal = (
                session.query(WorkoutTrackerDailyGoal)
                .filter_by(user_id=self.user_id, exercise_name=exercise_name)
                .first()
            )

            if existing_goal:
                # Update existing goal
                existing_goal.target_reps = target_reps
                existing_goal.target_sets = target_sets
                existing_goal.target_weight = target_weight
                existing_goal.target_duration = target_duration
                if muscle_group:
                    existing_goal.muscle_group = muscle_group
                existing_goal.updated_at = datetime.utcnow()
                existing_goal.active = True
                session.commit()

                return json.dumps(
                    {
                        "success": True,
                        "message": f"Daily goal for '{exercise_name}' updated successfully",
                        "goal": existing_goal.to_dict(),
                    }
                )
            else:
                # Create new goal
                goal = WorkoutTrackerDailyGoal(
                    user_id=self.user_id,
                    exercise_name=exercise_name,
                    target_reps=target_reps,
                    target_sets=target_sets,
                    target_weight=target_weight,
                    target_duration=target_duration,
                    muscle_group=muscle_group,
                )
                session.add(goal)
                session.commit()

                return json.dumps(
                    {
                        "success": True,
                        "message": f"Daily goal for '{exercise_name}' set successfully",
                        "goal": goal.to_dict(),
                    }
                )
        except Exception as e:
            session.rollback()
            logging.error(f"Error setting daily goal: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    def get_daily_goals(self, active_only: bool = True) -> str:
        """Get all daily goals for the user"""
        session = get_session()
        try:
            query = session.query(WorkoutTrackerDailyGoal).filter_by(
                user_id=self.user_id
            )
            if active_only:
                query = query.filter_by(active=True)

            goals = query.order_by(WorkoutTrackerDailyGoal.exercise_name).all()

            return json.dumps(
                {"success": True, "goals": [goal.to_dict() for goal in goals]}
            )
        except Exception as e:
            logging.error(f"Error getting daily goals: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    def update_daily_goal(
        self,
        exercise_name: str,
        target_reps: Optional[int] = None,
        target_sets: Optional[int] = None,
        target_weight: Optional[float] = None,
        target_duration: Optional[int] = None,
        muscle_group: Optional[str] = None,
        active: Optional[bool] = None,
    ) -> str:
        """Update a daily goal"""
        session = get_session()
        try:
            goal = (
                session.query(WorkoutTrackerDailyGoal)
                .filter_by(user_id=self.user_id, exercise_name=exercise_name)
                .first()
            )

            if not goal:
                return json.dumps({"success": False, "error": "Daily goal not found"})

            if target_reps is not None:
                goal.target_reps = target_reps
            if target_sets is not None:
                goal.target_sets = target_sets
            if target_weight is not None:
                goal.target_weight = target_weight
            if target_duration is not None:
                goal.target_duration = target_duration
            if muscle_group is not None:
                goal.muscle_group = muscle_group
            if active is not None:
                goal.active = active

            goal.updated_at = datetime.utcnow()
            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": f"Daily goal for '{exercise_name}' updated successfully",
                    "goal": goal.to_dict(),
                }
            )
        except Exception as e:
            session.rollback()
            logging.error(f"Error updating daily goal: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    def delete_daily_goal(self, exercise_name: str) -> str:
        """Delete a daily goal"""
        session = get_session()
        try:
            goal = (
                session.query(WorkoutTrackerDailyGoal)
                .filter_by(user_id=self.user_id, exercise_name=exercise_name)
                .first()
            )

            if not goal:
                return json.dumps({"success": False, "error": "Daily goal not found"})

            session.delete(goal)
            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": f"Daily goal for '{exercise_name}' deleted successfully",
                }
            )
        except Exception as e:
            session.rollback()
            logging.error(f"Error deleting daily goal: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    # Daily Completion Management Commands

    def mark_exercise_complete(
        self,
        exercise_name: str,
        completed_reps: int,
        completed_sets: int = 1,
        completed_weight: float = 0,
        completed_duration: int = 0,
        notes: str = "",
        completion_date: Optional[str] = None,
    ) -> str:
        """Mark an exercise as completed for today (or specified date)"""
        session = get_session()
        try:
            # Parse completion date or use today
            if completion_date:
                try:
                    comp_date = datetime.strptime(completion_date, "%Y-%m-%d").date()
                except ValueError:
                    return json.dumps(
                        {
                            "success": False,
                            "error": "Invalid date format. Use YYYY-MM-DD",
                        }
                    )
            else:
                comp_date = date.today()

            # Check if completion already exists for this date
            existing_completion = (
                session.query(WorkoutTrackerDailyCompletion)
                .filter_by(
                    user_id=self.user_id,
                    exercise_name=exercise_name,
                    completion_date=comp_date,
                )
                .first()
            )

            if existing_completion:
                # Update existing completion
                existing_completion.completed_reps = completed_reps
                existing_completion.completed_sets = completed_sets
                existing_completion.completed_weight = completed_weight
                existing_completion.completed_duration = completed_duration
                if notes:
                    existing_completion.notes = notes
                existing_completion.completed_at = datetime.utcnow()
                session.commit()

                return json.dumps(
                    {
                        "success": True,
                        "message": f"Updated completion for '{exercise_name}' on {comp_date}",
                        "completion": existing_completion.to_dict(),
                    }
                )
            else:
                # Create new completion
                completion = WorkoutTrackerDailyCompletion(
                    user_id=self.user_id,
                    exercise_name=exercise_name,
                    completion_date=comp_date,
                    completed_reps=completed_reps,
                    completed_sets=completed_sets,
                    completed_weight=completed_weight,
                    completed_duration=completed_duration,
                    notes=notes,
                )
                session.add(completion)
                session.commit()

                return json.dumps(
                    {
                        "success": True,
                        "message": f"Marked '{exercise_name}' as completed for {comp_date}",
                        "completion": completion.to_dict(),
                    }
                )
        except Exception as e:
            session.rollback()
            logging.error(f"Error marking exercise complete: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    def get_daily_progress(self, check_date: Optional[str] = None) -> str:
        """Get daily progress showing goals vs completions for a specific date"""
        session = get_session()
        try:
            # Parse check date or use today
            if check_date:
                try:
                    progress_date = datetime.strptime(check_date, "%Y-%m-%d").date()
                except ValueError:
                    return json.dumps(
                        {
                            "success": False,
                            "error": "Invalid date format. Use YYYY-MM-DD",
                        }
                    )
            else:
                progress_date = date.today()

            # Get all active daily goals
            goals = (
                session.query(WorkoutTrackerDailyGoal)
                .filter_by(user_id=self.user_id, active=True)
                .all()
            )

            # Get completions for the date
            completions = (
                session.query(WorkoutTrackerDailyCompletion)
                .filter_by(user_id=self.user_id, completion_date=progress_date)
                .all()
            )

            # Create completion lookup
            completion_dict = {comp.exercise_name: comp for comp in completions}

            progress = []
            for goal in goals:
                completion = completion_dict.get(goal.exercise_name)
                goal_data = goal.to_dict()
                goal_data["completed"] = completion is not None
                if completion:
                    goal_data["completion"] = completion.to_dict()
                    # Check if goal was met
                    goal_data["goal_met"] = (
                        completion.completed_reps >= goal.target_reps
                        and completion.completed_sets >= goal.target_sets
                    )
                else:
                    goal_data["completion"] = None
                    goal_data["goal_met"] = False

                progress.append(goal_data)

            return json.dumps(
                {
                    "success": True,
                    "date": progress_date.isoformat(),
                    "progress": progress,
                    "total_goals": len(goals),
                    "completed_goals": len([p for p in progress if p["completed"]]),
                    "goals_met": len([p for p in progress if p["goal_met"]]),
                }
            )
        except Exception as e:
            logging.error(f"Error getting daily progress: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    def get_weekly_progress(self, week_start: Optional[str] = None) -> str:
        """Get weekly progress showing daily completion rates"""
        session = get_session()
        try:
            # Parse week start or use current week
            if week_start:
                try:
                    start_date = datetime.strptime(week_start, "%Y-%m-%d").date()
                except ValueError:
                    return json.dumps(
                        {
                            "success": False,
                            "error": "Invalid date format. Use YYYY-MM-DD",
                        }
                    )
            else:
                today = date.today()
                start_date = today - timedelta(days=today.weekday())

            # Generate 7 days from start_date
            week_dates = [start_date + timedelta(days=i) for i in range(7)]

            # Get all active goals
            goals = (
                session.query(WorkoutTrackerDailyGoal)
                .filter_by(user_id=self.user_id, active=True)
                .all()
            )

            weekly_data = []
            for check_date in week_dates:
                # Get completions for this date
                completions = (
                    session.query(WorkoutTrackerDailyCompletion)
                    .filter_by(user_id=self.user_id, completion_date=check_date)
                    .all()
                )

                completion_dict = {comp.exercise_name: comp for comp in completions}

                day_progress = {
                    "date": check_date.isoformat(),
                    "day_of_week": check_date.strftime("%A"),
                    "total_goals": len(goals),
                    "completed_exercises": len(completions),
                    "goals_met": 0,
                    "exercises": [],
                }

                for goal in goals:
                    completion = completion_dict.get(goal.exercise_name)
                    exercise_data = {
                        "exercise_name": goal.exercise_name,
                        "target_reps": goal.target_reps,
                        "completed": completion is not None,
                        "completed_reps": (
                            completion.completed_reps if completion else 0
                        ),
                        "goal_met": False,
                    }

                    if completion:
                        exercise_data["goal_met"] = (
                            completion.completed_reps >= goal.target_reps
                            and completion.completed_sets >= goal.target_sets
                        )
                        if exercise_data["goal_met"]:
                            day_progress["goals_met"] += 1

                    day_progress["exercises"].append(exercise_data)

                weekly_data.append(day_progress)

            return json.dumps(
                {
                    "success": True,
                    "week_start": start_date.isoformat(),
                    "week_end": week_dates[-1].isoformat(),
                    "weekly_progress": weekly_data,
                }
            )
        except Exception as e:
            logging.error(f"Error getting weekly progress: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    def get_monthly_progress(self, month: Optional[str] = None) -> str:
        """Get monthly progress summary"""
        session = get_session()
        try:
            # Parse month or use current month
            if month:
                try:
                    month_date = datetime.strptime(month, "%Y-%m").date()
                    start_date = month_date.replace(day=1)
                except ValueError:
                    return json.dumps(
                        {"success": False, "error": "Invalid month format. Use YYYY-MM"}
                    )
            else:
                today = date.today()
                start_date = today.replace(day=1)

            # Calculate end date of month
            if start_date.month == 12:
                end_date = start_date.replace(
                    year=start_date.year + 1, month=1
                ) - timedelta(days=1)
            else:
                end_date = start_date.replace(month=start_date.month + 1) - timedelta(
                    days=1
                )

            # Get completions for the month
            completions = (
                session.query(WorkoutTrackerDailyCompletion)
                .filter(
                    and_(
                        WorkoutTrackerDailyCompletion.user_id == self.user_id,
                        WorkoutTrackerDailyCompletion.completion_date >= start_date,
                        WorkoutTrackerDailyCompletion.completion_date <= end_date,
                    )
                )
                .all()
            )

            # Get active goals
            goals = (
                session.query(WorkoutTrackerDailyGoal)
                .filter_by(user_id=self.user_id, active=True)
                .all()
            )

            # Calculate statistics by exercise
            exercise_stats = {}
            goal_dict = {goal.exercise_name: goal for goal in goals}

            for completion in completions:
                exercise_name = completion.exercise_name
                if exercise_name not in exercise_stats:
                    exercise_stats[exercise_name] = {
                        "exercise_name": exercise_name,
                        "total_completions": 0,
                        "total_reps": 0,
                        "goals_met": 0,
                        "days_in_month": (end_date - start_date).days + 1,
                        "target_reps": (
                            goal_dict.get(exercise_name, {}).target_reps
                            if exercise_name in goal_dict
                            else 0
                        ),
                    }

                stats = exercise_stats[exercise_name]
                stats["total_completions"] += 1
                stats["total_reps"] += completion.completed_reps

                # Check if daily goal was met
                if exercise_name in goal_dict:
                    goal = goal_dict[exercise_name]
                    if (
                        completion.completed_reps >= goal.target_reps
                        and completion.completed_sets >= goal.target_sets
                    ):
                        stats["goals_met"] += 1

            # Calculate completion rates
            for stats in exercise_stats.values():
                stats["completion_rate"] = (
                    stats["total_completions"] / stats["days_in_month"] * 100
                )
                stats["goal_achievement_rate"] = (
                    stats["goals_met"] / stats["days_in_month"] * 100
                )

            return json.dumps(
                {
                    "success": True,
                    "month": start_date.strftime("%Y-%m"),
                    "month_start": start_date.isoformat(),
                    "month_end": end_date.isoformat(),
                    "days_in_month": (end_date - start_date).days + 1,
                    "exercise_statistics": list(exercise_stats.values()),
                    "total_active_goals": len(goals),
                    "total_completions": len(completions),
                }
            )
        except Exception as e:
            logging.error(f"Error getting monthly progress: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()
