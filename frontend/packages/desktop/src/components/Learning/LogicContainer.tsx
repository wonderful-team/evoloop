import React from "react";
import { Plus } from "lucide-react";
import { Button } from "@evoloop/shared/components/ui/button";
import { useTranslation } from "react-i18next";

interface LogicContainerProps {
    children: React.ReactNode;
    onAdd: () => void;
}

export const LogicContainer: React.FC<LogicContainerProps> = ({
    children,
    onAdd,
}) => {
    const { t } = useTranslation();

    return (
        <div className="space-y-4 pl-8 border-l-2 border-dashed border-muted/50 ml-4 py-2 mt-2 -mb-2">
            {children}

            <Button
                variant="ghost"
                size="sm"
                className="w-full justify-start h-10 gap-2 border border-dashed border-muted hover:border-primary/30 hover:bg-primary/5 text-muted-foreground hover:text-primary rounded-xl transition-all"
                onClick={onAdd}
            >
                <Plus className="h-3.5 w-3.5" />
                <span className="text-[11px] font-bold uppercase tracking-wider">
                    {t("learning.editor.addInnerStep", "Add Step Inside")}
                </span>
            </Button>
        </div>
    );
};
