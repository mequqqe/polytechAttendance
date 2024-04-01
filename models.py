from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Attendance(Base):
    __tablename__ = 'attendances'
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, default=datetime.utcnow)
    status = Column(String, nullable=False)
    minutes_late = Column(Integer, nullable=True)  # Поле для хранения количества минут опоздания
    student_id = Column(Integer, ForeignKey('students.id'))
    student = relationship("Student", back_populates="attendances")


class Group(Base):
    __tablename__ = 'groups'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    students = relationship("Student", back_populates="group")

class Student(Base):
    __tablename__ = 'students'
    id = Column(Integer, primary_key=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    group_id = Column(Integer, ForeignKey('groups.id'))
    group = relationship("Group", back_populates="students")
    attendances = relationship("Attendance", back_populates="student")
