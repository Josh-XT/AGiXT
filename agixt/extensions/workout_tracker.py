"""
Workout Tracker Extension for AGiXT
This extension provides workout tracking capabilities with database persistence.
"""

import json
import logging
from datetime import datetime, date
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
)
from sqlalchemy.orm import relationship, declarative_base
from Extensions import Extensions
from DB import get_session, ExtensionDatabaseMixin, Base  # Import Base from DB.py


# Database Models for Workout Tracker
class WorkoutRoutine(Base):
    """Model for workout routines"""

    __tablename__ = "workout_routines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    difficulty = Column(String(50))  # e.g., 'beginner', 'intermediate', 'advanced'
    goal = Column(String(100))  # e.g., 'strength', 'endurance', 'flexibility'
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    active = Column(Boolean, default=True)

    # Relationship to exercises
    exercises = relationship(
        "WorkoutExercise", back_populates="routine", cascade="all, delete-orphan"
    )
    sessions = relationship(
        "WorkoutSession", back_populates="routine", cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "description": self.description,
            "difficulty": self.difficulty,
            "goal": self.goal,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "active": self.active,
        }


class WorkoutExercise(Base):
    """Model for exercises within a routine"""

    __tablename__ = "workout_exercises"

    id = Column(Integer, primary_key=True, autoincrement=True)
    routine_id = Column(Integer, ForeignKey("workout_routines.id"), nullable=False)
    name = Column(String(255), nullable=False)
    muscle_group = Column(String(100))  # e.g., 'chest', 'back', 'legs'
    sets = Column(Integer)
    reps = Column(Integer)
    weight = Column(Float)  # in kg or lbs
    duration = Column(Integer)  # in seconds for time-based exercises
    rest_time = Column(Integer)  # rest time in seconds
    order = Column(Integer, default=0)  # order in the routine
    notes = Column(Text)

    # Relationship to routine
    routine = relationship("WorkoutRoutine", back_populates="exercises")

    def to_dict(self):
        return {
            "id": self.id,
            "routine_id": self.routine_id,
            "name": self.name,
            "muscle_group": self.muscle_group,
            "sets": self.sets,
            "reps": self.reps,
            "weight": self.weight,
            "duration": self.duration,
            "rest_time": self.rest_time,
            "order": self.order,
            "notes": self.notes,
        }


class WorkoutSession(Base):
    """Model for workout sessions (completed workouts)"""

    __tablename__ = "workout_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    routine_id = Column(Integer, ForeignKey("workout_routines.id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    duration_minutes = Column(Integer)
    calories_burned = Column(Float)
    notes = Column(Text)
    performance_rating = Column(Integer)  # 1-5 rating

    # Relationship to routine
    routine = relationship("WorkoutRoutine", back_populates="sessions")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "routine_id": self.routine_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "duration_minutes": self.duration_minutes,
            "calories_burned": self.calories_burned,
            "notes": self.notes,
            "performance_rating": self.performance_rating,
        }


class DailyGoal(Base):
    """Model for daily exercise goals"""

    __tablename__ = "daily_goals"

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

    # Unique constraint to prevent duplicate goals for same exercise
    __table_args__ = (
        UniqueConstraint("user_id", "exercise_name", name="unique_user_exercise_goal"),
    )

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


class DailyCompletion(Base):
    """Model for tracking daily exercise completions"""

    __tablename__ = "daily_completions"

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

    # Unique constraint to prevent duplicate completions for same exercise on same day
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "exercise_name",
            "completion_date",
            name="unique_daily_completion",
        ),
    )

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

    # Register extension models for automatic table creation
    extension_models = [
        WorkoutRoutine,
        WorkoutExercise,
        WorkoutSession,
        DailyGoal,
        DailyCompletion,
    ]

    def __init__(self, **kwargs):
        self.AGENT = kwargs
        self.user_id = (
            self.AGENT["user"] if self.AGENT and "user" in self.AGENT else "default"
        )
        self.ApiClient = kwargs.get("ApiClient", None)

        # Register models with ExtensionDatabaseMixin
        self.register_models()

        # Define available commands
        self.commands = {
            # Routine Management
            "Create Workout Routine": self.create_routine,
            "Get Workout Routine": self.get_routine,
            "List Workout Routines": self.list_routines,
            "Update Workout Routine": self.update_routine,
            "Delete Workout Routine": self.delete_routine,
            # Exercise Management
            "Add Exercise to Routine": self.add_exercise,
            "Get Routine Exercises": self.get_exercises,
            "Update Exercise": self.update_exercise,
            "Delete Exercise": self.delete_exercise,
            # Session Management
            "Start Workout Session": self.start_session,
            "Complete Workout Session": self.complete_session,
            "Get Workout History": self.get_history,
            "Get Workout Statistics": self.get_statistics,
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

    # Routine Management Commands

    def create_routine(
        self,
        name: str,
        description: str = "",
        difficulty: str = "intermediate",
        goal: str = "general fitness",
    ) -> str:
        """Create a new workout routine"""
        session = get_session()
        try:
            routine = WorkoutRoutine(
                user_id=self.user_id,
                name=name,
                description=description,
                difficulty=difficulty,
                goal=goal,
            )
            session.add(routine)
            session.commit()
            return json.dumps(
                {
                    "success": True,
                    "message": f"Workout routine '{name}' created successfully",
                    "routine": routine.to_dict(),
                }
            )
        except Exception as e:
            session.rollback()
            logging.error(f"Error creating workout routine: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    def get_routine(self, routine_id: int) -> str:
        """Get a specific workout routine by ID"""
        session = get_session()
        try:
            routine = (
                session.query(WorkoutRoutine)
                .filter_by(id=routine_id, user_id=self.user_id)
                .first()
            )

            if not routine:
                return json.dumps({"success": False, "error": "Routine not found"})

            routine_data = routine.to_dict()
            routine_data["exercises"] = [ex.to_dict() for ex in routine.exercises]

            return json.dumps({"success": True, "routine": routine_data})
        except Exception as e:
            logging.error(f"Error getting workout routine: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    def list_routines(self, active_only: bool = True) -> str:
        """List all workout routines for the user"""
        session = get_session()
        try:
            query = session.query(WorkoutRoutine).filter_by(user_id=self.user_id)
            if active_only:
                query = query.filter_by(active=True)

            routines = query.order_by(WorkoutRoutine.created_at.desc()).all()

            return json.dumps(
                {
                    "success": True,
                    "routines": [routine.to_dict() for routine in routines],
                }
            )
        except Exception as e:
            logging.error(f"Error listing workout routines: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    def update_routine(
        self,
        routine_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        difficulty: Optional[str] = None,
        goal: Optional[str] = None,
        active: Optional[bool] = None,
    ) -> str:
        """Update an existing workout routine"""
        session = get_session()
        try:
            routine = (
                session.query(WorkoutRoutine)
                .filter_by(id=routine_id, user_id=self.user_id)
                .first()
            )

            if not routine:
                return json.dumps({"success": False, "error": "Routine not found"})

            if name is not None:
                routine.name = name
            if description is not None:
                routine.description = description
            if difficulty is not None:
                routine.difficulty = difficulty
            if goal is not None:
                routine.goal = goal
            if active is not None:
                routine.active = active

            routine.updated_at = datetime.utcnow()
            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": "Routine updated successfully",
                    "routine": routine.to_dict(),
                }
            )
        except Exception as e:
            session.rollback()
            logging.error(f"Error updating workout routine: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    def delete_routine(self, routine_id: int) -> str:
        """Delete a workout routine"""
        session = get_session()
        try:
            routine = (
                session.query(WorkoutRoutine)
                .filter_by(id=routine_id, user_id=self.user_id)
                .first()
            )

            if not routine:
                return json.dumps({"success": False, "error": "Routine not found"})

            session.delete(routine)
            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": f"Routine '{routine.name}' deleted successfully",
                }
            )
        except Exception as e:
            session.rollback()
            logging.error(f"Error deleting workout routine: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    # Exercise Management Commands

    def add_exercise(
        self,
        routine_id: int,
        name: str,
        muscle_group: str = "",
        sets: int = 3,
        reps: int = 10,
        weight: float = 0,
        duration: int = 0,
        rest_time: int = 60,
        order: int = 0,
        notes: str = "",
    ) -> str:
        """Add an exercise to a routine"""
        session = get_session()
        try:
            # Verify routine exists and belongs to user
            routine = (
                session.query(WorkoutRoutine)
                .filter_by(id=routine_id, user_id=self.user_id)
                .first()
            )

            if not routine:
                return json.dumps({"success": False, "error": "Routine not found"})

            exercise = WorkoutExercise(
                routine_id=routine_id,
                name=name,
                muscle_group=muscle_group,
                sets=sets,
                reps=reps,
                weight=weight,
                duration=duration,
                rest_time=rest_time,
                order=order,
                notes=notes,
            )
            session.add(exercise)
            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": f"Exercise '{name}' added to routine",
                    "exercise": exercise.to_dict(),
                }
            )
        except Exception as e:
            session.rollback()
            logging.error(f"Error adding exercise: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    def get_exercises(self, routine_id: int) -> str:
        """Get all exercises for a routine"""
        session = get_session()
        try:
            # Verify routine belongs to user
            routine = (
                session.query(WorkoutRoutine)
                .filter_by(id=routine_id, user_id=self.user_id)
                .first()
            )

            if not routine:
                return json.dumps({"success": False, "error": "Routine not found"})

            exercises = (
                session.query(WorkoutExercise)
                .filter_by(routine_id=routine_id)
                .order_by(WorkoutExercise.order)
                .all()
            )

            return json.dumps(
                {"success": True, "exercises": [ex.to_dict() for ex in exercises]}
            )
        except Exception as e:
            logging.error(f"Error getting exercises: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    def update_exercise(
        self,
        exercise_id: int,
        name: Optional[str] = None,
        muscle_group: Optional[str] = None,
        sets: Optional[int] = None,
        reps: Optional[int] = None,
        weight: Optional[float] = None,
        duration: Optional[int] = None,
        rest_time: Optional[int] = None,
        order: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> str:
        """Update an exercise"""
        session = get_session()
        try:
            # Get exercise and verify ownership through routine
            exercise = (
                session.query(WorkoutExercise)
                .join(WorkoutRoutine)
                .filter(
                    WorkoutExercise.id == exercise_id,
                    WorkoutRoutine.user_id == self.user_id,
                )
                .first()
            )

            if not exercise:
                return json.dumps({"success": False, "error": "Exercise not found"})

            if name is not None:
                exercise.name = name
            if muscle_group is not None:
                exercise.muscle_group = muscle_group
            if sets is not None:
                exercise.sets = sets
            if reps is not None:
                exercise.reps = reps
            if weight is not None:
                exercise.weight = weight
            if duration is not None:
                exercise.duration = duration
            if rest_time is not None:
                exercise.rest_time = rest_time
            if order is not None:
                exercise.order = order
            if notes is not None:
                exercise.notes = notes

            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": "Exercise updated successfully",
                    "exercise": exercise.to_dict(),
                }
            )
        except Exception as e:
            session.rollback()
            logging.error(f"Error updating exercise: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    def delete_exercise(self, exercise_id: int) -> str:
        """Delete an exercise from a routine"""
        session = get_session()
        try:
            # Get exercise and verify ownership through routine
            exercise = (
                session.query(WorkoutExercise)
                .join(WorkoutRoutine)
                .filter(
                    WorkoutExercise.id == exercise_id,
                    WorkoutRoutine.user_id == self.user_id,
                )
                .first()
            )

            if not exercise:
                return json.dumps({"success": False, "error": "Exercise not found"})

            exercise_name = exercise.name
            session.delete(exercise)
            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": f"Exercise '{exercise_name}' deleted successfully",
                }
            )
        except Exception as e:
            session.rollback()
            logging.error(f"Error deleting exercise: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    # Session Management Commands

    def start_session(self, routine_id: int, notes: str = "") -> str:
        """Start a new workout session"""
        session = get_session()
        try:
            # Verify routine exists and belongs to user
            routine = (
                session.query(WorkoutRoutine)
                .filter_by(id=routine_id, user_id=self.user_id)
                .first()
            )

            if not routine:
                return json.dumps({"success": False, "error": "Routine not found"})

            workout_session = WorkoutSession(
                user_id=self.user_id, routine_id=routine_id, notes=notes
            )
            session.add(workout_session)
            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": f"Started workout session for '{routine.name}'",
                    "session": workout_session.to_dict(),
                }
            )
        except Exception as e:
            session.rollback()
            logging.error(f"Error starting workout session: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    def complete_session(
        self,
        session_id: int,
        duration_minutes: int,
        calories_burned: float = 0,
        performance_rating: int = 3,
        notes: str = "",
    ) -> str:
        """Complete a workout session"""
        session = get_session()
        try:
            workout_session = (
                session.query(WorkoutSession)
                .filter_by(id=session_id, user_id=self.user_id)
                .first()
            )

            if not workout_session:
                return json.dumps({"success": False, "error": "Session not found"})

            workout_session.completed_at = datetime.utcnow()
            workout_session.duration_minutes = duration_minutes
            workout_session.calories_burned = calories_burned
            workout_session.performance_rating = performance_rating
            if notes:
                workout_session.notes = notes

            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": "Workout session completed",
                    "session": workout_session.to_dict(),
                }
            )
        except Exception as e:
            session.rollback()
            logging.error(f"Error completing workout session: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    def get_history(self, limit: int = 10) -> str:
        """Get workout history for the user"""
        session = get_session()
        try:
            sessions = (
                session.query(WorkoutSession)
                .filter_by(user_id=self.user_id)
                .order_by(WorkoutSession.started_at.desc())
                .limit(limit)
                .all()
            )

            history = []
            for workout_session in sessions:
                session_data = workout_session.to_dict()
                session_data["routine_name"] = workout_session.routine.name
                history.append(session_data)

            return json.dumps({"success": True, "history": history})
        except Exception as e:
            logging.error(f"Error getting workout history: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    def get_statistics(self) -> str:
        """Get workout statistics for the user"""
        session = get_session()
        try:
            from sqlalchemy import func

            # Total sessions
            total_sessions = (
                session.query(func.count(WorkoutSession.id))
                .filter_by(user_id=self.user_id)
                .scalar()
            )

            # Completed sessions
            completed_sessions = (
                session.query(func.count(WorkoutSession.id))
                .filter(
                    WorkoutSession.user_id == self.user_id,
                    WorkoutSession.completed_at.isnot(None),
                )
                .scalar()
            )

            # Total workout time
            total_minutes = (
                session.query(func.sum(WorkoutSession.duration_minutes))
                .filter_by(user_id=self.user_id)
                .scalar()
                or 0
            )

            # Total calories burned
            total_calories = (
                session.query(func.sum(WorkoutSession.calories_burned))
                .filter_by(user_id=self.user_id)
                .scalar()
                or 0
            )

            # Average performance rating
            avg_rating = (
                session.query(func.avg(WorkoutSession.performance_rating))
                .filter(
                    WorkoutSession.user_id == self.user_id,
                    WorkoutSession.performance_rating.isnot(None),
                )
                .scalar()
                or 0
            )

            # Most used routine
            most_used = (
                session.query(
                    WorkoutRoutine.name, func.count(WorkoutSession.id).label("count")
                )
                .join(WorkoutSession)
                .filter(WorkoutSession.user_id == self.user_id)
                .group_by(WorkoutRoutine.id)
                .order_by(func.count(WorkoutSession.id).desc())
                .first()
            )

            return json.dumps(
                {
                    "success": True,
                    "statistics": {
                        "total_sessions": total_sessions,
                        "completed_sessions": completed_sessions,
                        "total_workout_time_minutes": total_minutes,
                        "total_calories_burned": total_calories,
                        "average_performance_rating": (
                            float(avg_rating) if avg_rating else 0
                        ),
                        "most_used_routine": most_used[0] if most_used else None,
                    },
                }
            )
        except Exception as e:
            logging.error(f"Error getting workout statistics: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

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
                session.query(DailyGoal)
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
                goal = DailyGoal(
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
            query = session.query(DailyGoal).filter_by(user_id=self.user_id)
            if active_only:
                query = query.filter_by(active=True)

            goals = query.order_by(DailyGoal.exercise_name).all()

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
                session.query(DailyGoal)
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
                session.query(DailyGoal)
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
                session.query(DailyCompletion)
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
                completion = DailyCompletion(
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
                session.query(DailyGoal)
                .filter_by(user_id=self.user_id, active=True)
                .all()
            )

            # Get completions for the date
            completions = (
                session.query(DailyCompletion)
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
            from datetime import timedelta

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
                session.query(DailyGoal)
                .filter_by(user_id=self.user_id, active=True)
                .all()
            )

            weekly_data = []
            for check_date in week_dates:
                # Get completions for this date
                completions = (
                    session.query(DailyCompletion)
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
            from datetime import timedelta
            from sqlalchemy import func, and_

            # Parse month or use current month
            if month:
                try:
                    month_date = datetime.strptime(month, "%Y-%m").date()
                    start_date = month_date.replace(day=1)
                except ValueError:
                    return json.dumps(
                        {
                            "success": False,
                            "error": "Invalid month format. Use YYYY-MM",
                        }
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
                session.query(DailyCompletion)
                .filter(
                    and_(
                        DailyCompletion.user_id == self.user_id,
                        DailyCompletion.completion_date >= start_date,
                        DailyCompletion.completion_date <= end_date,
                    )
                )
                .all()
            )

            # Get active goals
            goals = (
                session.query(DailyGoal)
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
