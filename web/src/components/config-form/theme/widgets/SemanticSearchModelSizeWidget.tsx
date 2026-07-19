// Disables model_size and shows "N/A" when a GenAI provider is selected.
// Reads model via LiveFormDataContext so it re-runs even when RJSF's
// SchemaField memoization would skip this widget.
import type { WidgetProps } from "@rjsf/utils";
import { useContext } from "react";
import { useTranslation } from "react-i18next";
import {
  Select,
  SelectContent,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LiveFormDataContext } from "../../LiveFormDataContext";
import { getSizedFieldClassName } from "../utils";
import { SelectWidget } from "./SelectWidget";

export function SemanticSearchModelSizeWidget(props: WidgetProps) {
  const { t } = useTranslation(["views/settings"]);
  const liveFormData = useContext(LiveFormDataContext);
  const model = liveFormData?.model;
  const isProvider =
    typeof model === "string" &&
    model !== "" &&
    model !== "jinav1" &&
    model !== "jinav2";

  // model_size is ignored by the backend while a provider is selected, so the
  // field is only greyed out here. Rewriting the form data instead would leave
  // the section permanently dirty: the effective config always reports a
  // model_size, so the diff could never be cleared by saving.
  if (isProvider) {
    const fieldClassName = getSizedFieldClassName(props.options ?? {}, "sm");
    return (
      <Select value="" disabled>
        <SelectTrigger className={fieldClassName}>
          <SelectValue
            placeholder={t("configForm.semanticSearchModelSize.notApplicable", {
              defaultValue: "Not applicable for GenAI providers",
            })}
          />
        </SelectTrigger>
        <SelectContent />
      </Select>
    );
  }

  return <SelectWidget {...props} />;
}
