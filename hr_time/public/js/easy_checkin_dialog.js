import {EasyCheckinStatus} from "./easy_checkin_status";

export class EasyCheckinDialog {
    options = [];
    default = "";

    dashboard_number_card_refresh_button;

    /**
     * Preloads the current checkin status
     */
    preload() {
        frappe.call({
            method: "hr_time.api.flextime.api.get_easy_checkin_options",
            callback: (response) => {
                this.options = response.message.options;
                this.default = response.message.default;
            }
        });
    }

    /**
     * Shows the checkin dialog
     */
    show() {
        let checkin_dialog = this;

        let dialog = new frappe.ui.Dialog({
            title: __("Checkin"),
            fields: [
                {
                    label: 'Action',
                    fieldname: 'action',
                    fieldtype: 'Select',
                    options: this.options,
                    default: this.default
                }
            ],
            size: 'small', // small, large, extra-large
            primary_action_label: __("Submit"),
            primary_action(values) {
                frappe.call({
                    method: "hr_time.api.flextime.api.submit_easy_checkin",
                    args: {
                        action: values.action
                    },
                    callback: (response) => {
                        if (checkin_dialog.dashboard_number_card_refresh_button !== undefined) {
                            checkin_dialog.dashboard_number_card_refresh_button.click()
                        }
                        EasyCheckinStatus.render();
                        checkin_dialog.preload();

                        let message = "Successfully checked in";

                        switch (values.action) {
                            case "Break":
                                message = "Successfully checked out for break";
                                break;
                            case "End of work":
                                message = "Successfully checked out for end of work"
                                break;
                        }

                        frappe.show_alert({
                            message: __(message),
                            indicator: 'green'
                        }, 5);
                    }
                });

                dialog.hide();
            }
        });

        dialog.show()
    }

    /**
     * Binds events for numer card of dashboard
     */
    static prepare_dashboard() {
        let dialog = EasyCheckinDialog.singleton()

        document
            .getElementById("hr_time_number_card_checkin_status")
            .querySelector(".checkin_status")
            .onclick = function () {
            dialog.show();
        }

        dialog.dashboard_number_card_refresh_button = document
            .querySelector('[number_card_name="Checkin status"]')
            .querySelector('[data-action="action-refresh"]')
    }

    /**
     * Returns/Creates the singleton instance
     */
    static singleton() {
        if (window.easy_checkin_dialog === undefined) {
            window.easy_checkin_dialog = new EasyCheckinDialog();
        }

        return window.easy_checkin_dialog;
    }
}

