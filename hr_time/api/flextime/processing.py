import datetime

from hr_time.api import logger
from hr_time.api.attendance.repository import AttendanceRepository, Status, Attendance
from hr_time.api.check_in.repository import CheckinRepository
from hr_time.api.employee.repository import EmployeeRepository, TimeModel, Employee
from hr_time.api.flextime.break_time import BreakTimeRepository, BreakTimeDefinitions
from hr_time.api.flextime.definition import FlextimeDefinitionRepository, FlextimeDefinition
from hr_time.api.flextime.repository import FlextimeStatusRepository, FlextimeDailyStatus
from hr_time.api.holiday.repository import HolidayRepository
from hr_time.api.utils.clock import Clock
from hr_time.api.vacation.repository import VacationRepository


# Service for processing flextime account status
class FlexTimeProcessingService:
    clock: Clock

    daily_status: FlextimeStatusRepository
    employee: EmployeeRepository
    definitions: FlextimeDefinitionRepository
    break_times: BreakTimeRepository
    holidays: HolidayRepository
    attendance: AttendanceRepository
    vacation: VacationRepository
    checkin: CheckinRepository

    def __init__(self, clock: Clock, daily_status: FlextimeStatusRepository, employee: EmployeeRepository,
                 definitions: FlextimeDefinitionRepository, break_times: BreakTimeRepository,
                 holidays: HolidayRepository, attendance: AttendanceRepository, vacation: VacationRepository,
                 checkin: CheckinRepository):
        self.attendance = attendance
        self.vacation = vacation
        self.clock = clock
        self.daily_status = daily_status
        self.employee = employee
        self.definitions = definitions
        self.break_times = break_times
        self.holidays = holidays
        self.checkin = checkin

    # Creates an instance for productive usage
    @staticmethod
    def prod():
        return FlexTimeProcessingService(Clock(), FlextimeStatusRepository(), EmployeeRepository(),
                                         FlextimeDefinitionRepository(), BreakTimeRepository(), HolidayRepository(),
                                         AttendanceRepository(), VacationRepository(), CheckinRepository())

    # Starts the processing/generation of daily flextime status documents
    def process_daily_status(self):
        employees = self.employee.get_all()
        break_times = self.break_times.get_definitions()

        for employee in employees:
            logger.info("Starting flextime processing of employee " + employee.id)

            if employee.time_model is not TimeModel.Flextime:
                logger.info("Skipping employee " + employee.id + ", as time model is not flextime")
                continue

            definition = self.definitions.get_by_grade(employee.grade)

            if definition is None:
                logger.info(
                    "Skipping employee " + employee.id + ", as no flextime definition was found for grade " + str(
                        employee.grade))
                continue

            self._process_employee(employee, break_times, definition)

    def _process_employee(self, employee: Employee, break_time: BreakTimeDefinitions, definitions: FlextimeDefinition):
        current_day = self.daily_status.get_latest_status_date(employee)

        if current_day is None:
            current_day = employee.join_date
        else:
            current_day += datetime.timedelta(days=1)

        flextime_balance = self.daily_status.get_flextime_balance(employee.id)
        logger.info(employee.id + ": Found current flextime balance of " + str(flextime_balance) + " hours")

        while current_day < self.clock.date_today():
            logger.info(employee.id + ": Processing day " + current_day.isoformat())

            attendance = self.attendance.get(employee.id, current_day)
            target_working_time = definitions.get_for_weekday(current_day.weekday()).working_time

            if self.holidays.is_holiday(current_day):
                target_working_time = 0
                logger.info("Detected " + str(current_day) + " as holiday and set target working time to zero")
            elif attendance is not None and attendance.status is Status.OnLeave:
                request = self.vacation.get_request(employee.id, current_day)

                if request is None:
                    target_working_time = 0
                    logger.info("Detected " + str(current_day) + " as regular leave, but found no vacation request")
                elif request.is_half_day:
                    target_working_time /= 2
                    logger.info("Detected " + str(current_day) + " as regular leave with half-day vacation request")
                else:
                    target_working_time = 0
                    logger.info("Detected " + str(current_day) + " as regular leave with full-day vacation request")
            else:
                logger.info("Set target working time to " + str(target_working_time))

            status = FlextimeDailyStatus(
                employee.id,
                current_day,
                target_working_time
            )

            durations = self.checkin.get(current_day, employee.id).get_durations()
            logger.info("Found " + str(len(durations)) + " durations")

            for duration in durations:
                status.insert_duration(duration)

            status.calculate(break_time, definitions.forced_insufficient_break_time, employee.is_minor(),
                             flextime_balance)
            self.daily_status.add(status)

            if attendance is None:
                self._create_attendance(status)

            flextime_balance = status.time_balance
            logger.info("New flextime balance: " + str(flextime_balance))

            current_day += datetime.timedelta(days=1)

    def _create_attendance(self, flextime_status: FlextimeDailyStatus):
        if flextime_status.target_working_time == 0:
            return

        if flextime_status.total_working_hours > 0:
            status = Status.Present
        else:
            status = Status.Absent

        self.attendance.create(Attendance(flextime_status.employee_id, flextime_status.date, status, None))
