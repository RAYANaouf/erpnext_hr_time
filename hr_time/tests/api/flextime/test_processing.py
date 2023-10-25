import datetime
import unittest
from unittest.mock import MagicMock

from hr_time.api.check_in.list import CheckinList
from hr_time.api.check_in.repository import CheckinRepository
from hr_time.api.employee.repository import EmployeeRepository, Employee, TimeModel
from hr_time.api.flextime.brake_time import BreakTimeRepository, BrakeTimeDefinitions
from hr_time.api.flextime.definition import FlextimeDefinitionRepository, FlextimeDefinition, WorkdayDefinition
from hr_time.api.flextime.processing import FlexTimeProcessingService
from hr_time.api.flextime.repository import FlextimeStatusRepository
from hr_time.api.holiday.repository import HolidayRepository
from hr_time.api.utils.clock import Clock


class FlextimeProcessingTest(unittest.TestCase):
    flextime_definition: FlextimeDefinition

    clock: Clock
    daily_status: FlextimeStatusRepository
    employee: EmployeeRepository
    definitions: FlextimeDefinitionRepository
    brake_times: BreakTimeRepository
    holidays: HolidayRepository
    checkin: CheckinRepository

    service: FlexTimeProcessingService

    def setUp(self):
        super().setUp()
        self.flextime_definition = FlextimeDefinition(3600)
        self.flextime_definition.insert(WorkdayDefinition(0, 28_800, datetime.timedelta(), datetime.timedelta()))
        self.flextime_definition.insert(WorkdayDefinition(1, 28_800, datetime.timedelta(), datetime.timedelta()))
        self.flextime_definition.insert(WorkdayDefinition(2, 28_800, datetime.timedelta(), datetime.timedelta()))
        self.flextime_definition.insert(WorkdayDefinition(3, 28_800, datetime.timedelta(), datetime.timedelta()))
        self.flextime_definition.insert(WorkdayDefinition(4, 21_600, datetime.timedelta(), datetime.timedelta()))
        self.flextime_definition.insert(WorkdayDefinition(5, 0, datetime.timedelta(), datetime.timedelta()))
        self.flextime_definition.insert(WorkdayDefinition(6, 0, datetime.timedelta(), datetime.timedelta()))

        self.clock = Clock()
        self.daily_status = FlextimeStatusRepository()
        self.employee = EmployeeRepository()
        self.definitions = FlextimeDefinitionRepository()
        self.brake_times = BreakTimeRepository()
        self.holidays = HolidayRepository()
        self.checkin = CheckinRepository()

        self.service = FlexTimeProcessingService(self.clock, self.daily_status, self.employee, self.definitions,
                                                 self.brake_times,
                                                 self.holidays, self.checkin)

    def test_process_daily_status_no_flextime_time_model(self):
        self.brake_times.get_definitions = MagicMock(return_value=BrakeTimeDefinitions())

        self.employee.get_all = MagicMock(return_value=[
            Employee("001", TimeModel.Undefined, "Executive", datetime.date(1990, 5, 21), datetime.date.today())
        ])

        self.daily_status.add = MagicMock()

        self.service.process_daily_status()

        self.employee.get_all.assert_called_once()
        self.daily_status.add.assert_not_called()

    def test_process_daily_status_no_flextime_def_found(self):
        self.brake_times.get_definitions = MagicMock(return_value=BrakeTimeDefinitions())

        self.employee.get_all = MagicMock(return_value=[
            Employee("001", TimeModel.Flextime, "Executive", datetime.date(1990, 5, 21), datetime.date.today())
        ])

        self.definitions.get_by_grade = MagicMock(return_value=None)
        self.daily_status.add = MagicMock()

        self.service.process_daily_status()

        self.definitions.get_by_grade.assert_called_once()
        self.daily_status.add.assert_not_called()

    def test_process_daily_status_already_up2date(self):
        self.brake_times.get_definitions = MagicMock(return_value=BrakeTimeDefinitions())

        employee = Employee("001", TimeModel.Flextime, "Executive", datetime.date(1990, 5, 21), datetime.date.today())
        self.employee.get_all = MagicMock(return_value=[employee])

        self.definitions.get_by_grade = MagicMock(return_value=self.flextime_definition)

        today = datetime.date(2023, 10, 16)
        self.clock.date_today = MagicMock(return_value=today)

        self.daily_status.get_latest_status_date = MagicMock(return_value=datetime.date(2023, 10, 15))
        self.daily_status.get_flextime_balance = MagicMock(return_value=0)
        self.daily_status.add = MagicMock()

        self.service.process_daily_status()

        self.daily_status.get_latest_status_date.assert_called_once()
        self.daily_status.get_latest_status_date.assert_called_once_with(employee)

        self.daily_status.add.assert_not_called()

    def test_process_daily_status_holiday(self):
        self.brake_times.get_definitions = MagicMock(return_value=BrakeTimeDefinitions())

        employee = Employee("001", TimeModel.Flextime, "Executive", datetime.date(1990, 5, 21), datetime.date.today())
        self.employee.get_all = MagicMock(return_value=[employee])

        self.definitions.get_by_grade = MagicMock(return_value=self.flextime_definition)

        today = datetime.date(2023, 10, 17)
        self.clock.date_today = MagicMock(return_value=today)

        self.daily_status.get_latest_status_date = MagicMock(return_value=datetime.date(2023, 10, 15))
        self.daily_status.get_flextime_balance = MagicMock(return_value=1.5)
        self.daily_status.add = MagicMock()

        self.holidays.is_holiday = MagicMock(return_value=True)

        self.checkin.get = MagicMock(return_value=CheckinList([]))

        self.service.process_daily_status()

        self.holidays.is_holiday.assert_called_once_with(datetime.date(2023, 10, 16))

        self.daily_status.add.assert_called_once()
        self.assertEqual("001", self.daily_status.add.call_args.args[0].employee_id)
        self.assertEqual(datetime.date(2023, 10, 16), self.daily_status.add.call_args.args[0].date)
        self.assertEqual(0, self.daily_status.add.call_args.args[0].total_working_hours)
        self.assertEqual(1.5, self.daily_status.add.call_args.args[0].time_balance)
        self.assertEqual(0, self.daily_status.add.call_args.args[0].target_working_time)

    def test_process_join_date_used(self):
        self.brake_times.get_definitions = MagicMock(return_value=BrakeTimeDefinitions())

        employee = Employee("001", TimeModel.Flextime, "Executive", datetime.date(1990, 5, 21),
                            datetime.date(2023, 10, 1))
        self.employee.get_all = MagicMock(return_value=[employee])

        self.definitions.get_by_grade = MagicMock(return_value=self.flextime_definition)

        today = datetime.date(2023, 10, 5)
        self.clock.date_today = MagicMock(return_value=today)

        self.daily_status.get_latest_status_date = MagicMock(return_value=None)
        self.daily_status.get_flextime_balance = MagicMock(return_value=0)
        self.daily_status.add = MagicMock()

        self.holidays.is_holiday = MagicMock(return_value=False)

        self.checkin.get = MagicMock(return_value=CheckinList([]))

        self.service.process_daily_status()

        self.holidays.is_holiday.assert_called()
        self.assertEqual(datetime.date(2023, 10, 1), self.holidays.is_holiday.call_args_list[0].args[0])
        self.assertEqual(datetime.date(2023, 10, 2), self.holidays.is_holiday.call_args_list[1].args[0])
        self.assertEqual(datetime.date(2023, 10, 3), self.holidays.is_holiday.call_args_list[2].args[0])
        self.assertEqual(datetime.date(2023, 10, 4), self.holidays.is_holiday.call_args_list[3].args[0])

        self.daily_status.add.assert_called()
        self.assertEqual(datetime.date(2023, 10, 1), self.daily_status.add.call_args_list[0].args[0].date)
        self.assertEqual(datetime.date(2023, 10, 2), self.daily_status.add.call_args_list[1].args[0].date)
        self.assertEqual(datetime.date(2023, 10, 3), self.daily_status.add.call_args_list[2].args[0].date)
        self.assertEqual(datetime.date(2023, 10, 4), self.daily_status.add.call_args_list[3].args[0].date)

    def test_process_correct_target_working_time_and_balance(self):
        self.brake_times.get_definitions = MagicMock(return_value=BrakeTimeDefinitions())

        employee = Employee("001", TimeModel.Flextime, "Executive", datetime.date(1990, 5, 21),
                            datetime.date(2023, 10, 1))
        self.employee.get_all = MagicMock(return_value=[employee])

        self.definitions.get_by_grade = MagicMock(return_value=self.flextime_definition)

        today = datetime.date(2023, 10, 16)
        self.clock.date_today = MagicMock(return_value=today)

        self.daily_status.get_latest_status_date = MagicMock(return_value=datetime.date(2023, 10, 8))
        self.daily_status.get_flextime_balance = MagicMock(return_value=2.1)
        self.daily_status.add = MagicMock()

        self.holidays.is_holiday = MagicMock(return_value=False)

        self.checkin.get = MagicMock(return_value=CheckinList([]))

        self.service.process_daily_status()

        self.daily_status.add.assert_called()
        self.assertEqual(datetime.date(2023, 10, 9), self.daily_status.add.call_args_list[0].args[0].date)
        self.assertEqual(28_800, self.daily_status.add.call_args_list[0].args[0].target_working_time)
        self.assertEqual(-5.9, self.daily_status.add.call_args_list[0].args[0].time_balance)

        self.assertEqual(datetime.date(2023, 10, 10), self.daily_status.add.call_args_list[1].args[0].date)
        self.assertEqual(28_800, self.daily_status.add.call_args_list[1].args[0].target_working_time)
        self.assertEqual(-13.9, self.daily_status.add.call_args_list[1].args[0].time_balance)

        self.assertEqual(datetime.date(2023, 10, 11), self.daily_status.add.call_args_list[2].args[0].date)
        self.assertEqual(28_800, self.daily_status.add.call_args_list[2].args[0].target_working_time)
        self.assertEqual(-21.9, self.daily_status.add.call_args_list[2].args[0].time_balance)

        self.assertEqual(datetime.date(2023, 10, 12), self.daily_status.add.call_args_list[3].args[0].date)
        self.assertEqual(28_800, self.daily_status.add.call_args_list[3].args[0].target_working_time)
        self.assertEqual(-29.9, self.daily_status.add.call_args_list[3].args[0].time_balance)

        self.assertEqual(datetime.date(2023, 10, 13), self.daily_status.add.call_args_list[4].args[0].date)
        self.assertEqual(21_600, self.daily_status.add.call_args_list[4].args[0].target_working_time)
        self.assertEqual(-35.9, self.daily_status.add.call_args_list[4].args[0].time_balance)

        self.assertEqual(datetime.date(2023, 10, 14), self.daily_status.add.call_args_list[5].args[0].date)
        self.assertEqual(0, self.daily_status.add.call_args_list[5].args[0].target_working_time)
        self.assertEqual(-35.9, self.daily_status.add.call_args_list[5].args[0].time_balance)

        self.assertEqual(datetime.date(2023, 10, 15), self.daily_status.add.call_args_list[6].args[0].date)
        self.assertEqual(0, self.daily_status.add.call_args_list[6].args[0].target_working_time)
        self.assertEqual(-35.9, self.daily_status.add.call_args_list[6].args[0].time_balance)