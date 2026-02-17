/**
 * Filter form timezone conversion handler.
 *
 * Intercepts filter-form submissions to convert bare YYYY-MM-DD date inputs
 * into timezone-aware ISO 8601 strings. HTML date inputs only accept YYYY-MM-DD
 * format, so hidden inputs carry the ISO values for the server.
 *
 * Also adjusts server-generated UTC default dates to local timezone on page load.
 */
(function() {
    'use strict';

    /**
     * Replace a date input with a hidden input carrying the ISO value.
     * Disables the visible input so it is not submitted.
     */
    function replaceWithHidden(form, input, isoValue) {
        var hidden = document.createElement('input');
        hidden.type = 'hidden';
        hidden.name = input.name;
        hidden.value = isoValue;
        input.disabled = true;
        form.appendChild(hidden);
    }

    // Intercept filter form submissions
    document.addEventListener('submit', function(e) {
        var form = e.target;
        if (!form.classList.contains('filter-form')) return;

        var fromInput = form.querySelector('input[name="from_date"]');
        var toInput = form.querySelector('input[name="to_date"]');

        if (fromInput && fromInput.value && fromInput.value.indexOf('T') === -1) {
            replaceWithHidden(form, fromInput, dateInputToStartOfDayUTC(fromInput.value));
        }
        if (toInput && toInput.value && toInput.value.indexOf('T') === -1) {
            replaceWithHidden(form, toInput, dateInputToEndOfDayUTC(toInput.value));
        }
    });

    // On page load: adjust date inputs to show correct local dates.
    // The server extracts YYYY-MM-DD from the UTC portion of ISO strings,
    // which may differ from the local date (e.g. "2026-02-16T15:00Z" is Feb 17 in JST).
    document.addEventListener('DOMContentLoaded', function() {
        var params = new URLSearchParams(window.location.search);
        if (!params.has('from_date') && !params.has('to_date')) {
            // No date params: adjust server UTC defaults to local dates
            document.querySelectorAll('.filter-form').forEach(function(form) {
                var toInput = form.querySelector('input[name="to_date"]');
                if (toInput && toInput.value) {
                    toInput.value = getLocalDateString();
                }
            });
        } else {
            // Date params present: if they're ISO strings, convert to local dates for display
            var fromParam = params.get('from_date');
            var toParam = params.get('to_date');

            document.querySelectorAll('.filter-form').forEach(function(form) {
                if (fromParam && fromParam.indexOf('T') !== -1) {
                    var fromInput = form.querySelector('input[name="from_date"]');
                    if (fromInput) {
                        fromInput.value = getDateInputValue(fromParam);
                    }
                }
                if (toParam && toParam.indexOf('T') !== -1) {
                    var toInput = form.querySelector('input[name="to_date"]');
                    if (toInput) {
                        toInput.value = getDateInputValue(toParam);
                    }
                }
            });
        }
    });
})();
