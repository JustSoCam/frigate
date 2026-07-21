import {
  AllGroupsStreamingSettings,
  FrigateConfig,
  GroupStreamingSettings,
  PanelConfig,
  PanelTileConfig,
} from "@/types/frigateConfig";
import { isDesktop, isMobile } from "react-device-detect";
import useSWR from "swr";
import { MdHome } from "react-icons/md";
import { Button, buttonVariants } from "../ui/button";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { AnimatePresence, motion } from "framer-motion";
import { HiDotsHorizontal } from "react-icons/hi";
import { IoClose } from "react-icons/io5";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";
import { LuPencil, LuPlus } from "react-icons/lu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Input } from "../ui/input";
import { Separator } from "../ui/separator";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuPortal,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../ui/alert-dialog";
import axios from "axios";
import { HiOutlineDotsVertical, HiTrash } from "react-icons/hi";
import IconWrapper from "../ui/icon-wrapper";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Toaster } from "@/components/ui/sonner";
import { toast } from "sonner";
import ActivityIndicator from "../indicators/activity-indicator";
import { useUserPersistence } from "@/hooks/use-user-persistence";
import { TooltipPortal } from "@radix-ui/react-tooltip";
import { cn } from "@/lib/utils";
import * as LuIcons from "react-icons/lu";
import IconPicker, { IconName, IconRenderer } from "../icons/IconPicker";
import { isValidIconName } from "@/utils/iconUtil";
import {
  MobilePage,
  MobilePageContent,
  MobilePageDescription,
  MobilePageHeader,
  MobilePageTitle,
} from "../mobile/MobilePage";

import { CameraStreamingDialog } from "../settings/CameraStreamingDialog";
import { DialogTrigger } from "@radix-ui/react-dialog";
import { useStreamingSettings } from "@/context/streaming-settings-provider";
import { Trans, useTranslation } from "react-i18next";
import { CameraNameLabel } from "../camera/FriendlyNameLabel";
import { useAllowedCameras } from "@/hooks/use-allowed-cameras";
import { useHasFullCameraAccess } from "@/hooks/use-has-full-camera-access";
import { useIsAdmin } from "@/hooks/use-is-admin";
import { useUserPersistedOverlayState } from "@/hooks/use-overlay-state";
import { getConfiguredPanels } from "@/utils/panelUtil";
import AutoUpdatingCameraImage from "../camera/AutoUpdatingCameraImage";
import { Slider } from "../ui/slider";

type PanelSelectorProps = {
  className?: string;
};

export function PanelSelector({ className }: PanelSelectorProps) {
  const { t } = useTranslation(["components/camera"]);
  const { data: config } = useSWR<FrigateConfig>("config");
  const allowedCameras = useAllowedCameras();
  const hasFullCameraAccess = useHasFullCameraAccess();
  const isAdmin = useIsAdmin();

  // tooltip

  const [tooltip, setTooltip] = useState<string>();
  const [timeoutId, setTimeoutId] = useState<NodeJS.Timeout>();
  const showTooltip = useCallback(
    (newTooltip: string | undefined) => {
      if (!newTooltip) {
        setTooltip(newTooltip);

        if (timeoutId) {
          clearTimeout(timeoutId);
        }
      } else {
        setTimeoutId(setTimeout(() => setTooltip(newTooltip), 500));
      }
    },
    [timeoutId],
  );

  // groups - use user-namespaced key for persistence to avoid cross-user conflicts

  const [group, setGroup, , deleteGroup] = useUserPersistedOverlayState(
    "cameraGroup",
    "default" as string,
  );

  const groups = useMemo(() => {
    if (!config) {
      return [];
    }

    const allGroups = getConfiguredPanels(config);

    // If custom role, filter out groups where user has no accessible cameras
    if (!hasFullCameraAccess) {
      return allGroups
        .filter(([, groupConfig]) => {
          // Check if user has access to at least one camera in this group
          return groupConfig.tiles.some((tile) =>
            allowedCameras.includes(tile.camera),
          );
        })
        .sort((a, b) => a[1].order - b[1].order);
    }

    return allGroups.sort((a, b) => a[1].order - b[1].order);
  }, [config, allowedCameras, hasFullCameraAccess]);

  // add group

  const [addGroup, setAddGroup] = useState(false);

  // mobile overflow reveal - the group strip sits left of the logo and is
  // clipped (not scrollable) when there are too many groups, so render only
  // the buttons that fully fit and surface a kebab next to the last visible
  // one that expands a panel revealing all of them

  const [expanded, setExpanded] = useState(false);
  // null => all buttons fit, render them all with no kebab; a number => only
  // that many fit alongside the kebab
  const [visibleCount, setVisibleCount] = useState<number | null>(null);
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const measureRef = useRef<HTMLDivElement | null>(null);

  useLayoutEffect(() => {
    if (isDesktop) {
      return;
    }

    const wrapper = wrapperRef.current;
    const measure = measureRef.current;

    if (!wrapper || !measure) {
      return;
    }

    const gap = 8; // gap-2 between buttons in the strip
    const wrapperGap = 4; // gap-1 between the strip and the kebab

    const compute = () => {
      const buttons = Array.from(measure.children) as HTMLElement[];

      if (buttons.length === 0) {
        return;
      }

      // the trailing child of the measurement row is a kebab clone
      const kebab = buttons[buttons.length - 1];
      const groupButtons = buttons.slice(0, -1);
      const available = wrapper.clientWidth;
      const fullWidth =
        groupButtons.reduce((sum, el) => sum + el.offsetWidth, 0) +
        Math.max(groupButtons.length - 1, 0) * gap;

      if (fullWidth <= available) {
        setVisibleCount(null);
        return;
      }

      const budget = available - kebab.offsetWidth - wrapperGap;
      let used = 0;
      let count = 0;

      for (const el of groupButtons) {
        const next = (count === 0 ? 0 : gap) + el.offsetWidth;

        if (used + next <= budget) {
          used += next;
          count += 1;
        } else {
          break;
        }
      }

      setVisibleCount(Math.max(count, 1));
    };

    compute();

    const observer = new ResizeObserver(compute);
    observer.observe(wrapper);

    return () => observer.disconnect();
  }, [groups, isAdmin]);

  const groupButtons = (afterSelect?: () => void) => {
    const buttons = [
      <Button
        key="default-group"
        className={cn(
          "shrink-0",
          group == "default"
            ? "bg-blue-900 bg-opacity-60 text-selected focus:bg-blue-900 focus:bg-opacity-60"
            : "bg-secondary text-secondary-foreground",
        )}
        aria-label={t("menu.live.allCameras", { ns: "common" })}
        size="sm"
        onClick={() => {
          if (group) {
            setGroup("default", true);
          }
          afterSelect?.();
        }}
      >
        <MdHome className="size-5" />
      </Button>,
      ...groups.map(([name, config]) => (
        <Button
          key={name}
          className={cn(
            "shrink-0",
            group == name
              ? "bg-blue-900 bg-opacity-60 text-selected focus:bg-blue-900 focus:bg-opacity-60"
              : "bg-secondary text-secondary-foreground",
          )}
          aria-label={t("group.label")}
          size="sm"
          onClick={() => {
            setGroup(name, group != "default");
            afterSelect?.();
          }}
        >
          {config && config.icon && isValidIconName(config.icon) && (
            <IconRenderer icon={LuIcons[config.icon]} className="size-5" />
          )}
        </Button>
      )),
    ];

    if (isAdmin) {
      buttons.push(
        <Button
          key="add-group"
          className="shrink-0 bg-secondary text-muted-foreground"
          aria-label={t("group.add")}
          size="sm"
          onClick={() => {
            setAddGroup(true);
            afterSelect?.();
          }}
        >
          <LuPencil className="size-5 text-primary-variant" />
        </Button>,
      );
    }

    return buttons;
  };

  return (
    <>
      <PanelManagementDialog
        open={addGroup}
        setOpen={setAddGroup}
        currentGroups={groups}
        activeGroup={group}
        setGroup={setGroup}
        deleteGroup={deleteGroup}
        isAdmin={isAdmin}
      />
      {isDesktop ? (
        <div
          className={cn(
            "flex flex-col items-center justify-start gap-2",
            className,
          )}
        >
          <Tooltip open={tooltip == "default"}>
            <TooltipTrigger asChild>
              <Button
                className={
                  group == "default"
                    ? "bg-blue-900 bg-opacity-60 text-selected focus:bg-blue-900 focus:bg-opacity-60"
                    : "bg-secondary text-secondary-foreground focus:bg-secondary focus:text-secondary-foreground"
                }
                aria-label={t("menu.live.allCameras", { ns: "common" })}
                size="xs"
                onClick={() => (group ? setGroup("default", true) : null)}
                onMouseEnter={() => showTooltip("default")}
                onMouseLeave={() => showTooltip(undefined)}
              >
                <MdHome className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipPortal>
              <TooltipContent className="" side="right">
                {t("menu.live.allCameras", { ns: "common" })}
              </TooltipContent>
            </TooltipPortal>
          </Tooltip>
          {groups.map(([name, config]) => {
            return (
              <Tooltip key={name} open={tooltip == name}>
                <TooltipTrigger asChild>
                  <Button
                    className={
                      group == name
                        ? "bg-blue-900 bg-opacity-60 text-selected focus:bg-blue-900 focus:bg-opacity-60"
                        : "bg-secondary text-secondary-foreground"
                    }
                    aria-label={t("group.label")}
                    size="xs"
                    onClick={() => setGroup(name, group != "default")}
                    onMouseEnter={() => showTooltip(name)}
                    onMouseLeave={() => showTooltip(undefined)}
                  >
                    {config && config.icon && isValidIconName(config.icon) && (
                      <IconRenderer
                        icon={LuIcons[config.icon]}
                        className="size-4"
                      />
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipPortal>
                  <TooltipContent className="smart-capitalize" side="right">
                    {name}
                  </TooltipContent>
                </TooltipPortal>
              </Tooltip>
            );
          })}

          {isAdmin && (
            <Tooltip open={tooltip == "edit"}>
              <TooltipTrigger asChild>
                <Button
                  className="bg-secondary text-muted-foreground"
                  aria-label={t("group.editGroups")}
                  size="xs"
                  onClick={() => setAddGroup(true)}
                  onMouseEnter={() => showTooltip("edit")}
                  onMouseLeave={() => showTooltip(undefined)}
                >
                  <LuPencil className="size-4 text-primary-variant" />
                </Button>
              </TooltipTrigger>
              <TooltipPortal>
                <TooltipContent side="right">
                  {t("group.editGroups")}
                </TooltipContent>
              </TooltipPortal>
            </Tooltip>
          )}
        </div>
      ) : (
        <div
          ref={wrapperRef}
          className={cn("flex min-w-0 items-center gap-1", className)}
        >
          <div className="flex min-w-0 items-center gap-2 overflow-hidden whitespace-nowrap">
            {visibleCount == null
              ? groupButtons()
              : groupButtons().slice(0, visibleCount)}
          </div>
          {visibleCount != null && (
            <Button
              variant="ghost"
              size="sm"
              className="shrink-0 px-2 text-secondary-foreground"
              aria-label={t("group.showAll")}
              onClick={() => setExpanded(true)}
            >
              <HiDotsHorizontal className="size-5" />
            </Button>
          )}

          {/* invisible row used only to measure natural button widths so we
              can render exactly the buttons that fully fit */}
          <div
            className="pointer-events-none absolute left-0 top-0 h-0 w-0 overflow-hidden"
            aria-hidden
            inert
          >
            <div ref={measureRef} className="flex w-max items-center gap-2">
              {groupButtons()}
              <Button variant="ghost" size="sm" className="px-2">
                <HiDotsHorizontal className="size-5" />
              </Button>
            </div>
          </div>

          {expanded && (
            <div
              className="fixed inset-0 z-20"
              onClick={() => setExpanded(false)}
            />
          )}
          <AnimatePresence>
            {expanded && (
              <motion.div
                key="group-overlay"
                className="absolute inset-x-0 top-0 z-30 bg-background py-1 shadow-lg"
                initial={{ clipPath: "inset(0 100% 0 0)" }}
                animate={{ clipPath: "inset(0 0% 0 0)" }}
                exit={{ clipPath: "inset(0 100% 0 0)" }}
                transition={{ duration: 0.2, ease: "easeInOut" }}
              >
                <div className="flex flex-wrap items-center gap-2">
                  {groupButtons(() => setExpanded(false))}
                  <Button
                    variant="ghost"
                    size="sm"
                    className="ml-auto shrink-0 px-2 text-secondary-foreground"
                    aria-label={t("group.showLess")}
                    onClick={() => setExpanded(false)}
                  >
                    <IoClose className="size-5" />
                  </Button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </>
  );
}

type PanelManagementDialogProps = {
  open: boolean;
  setOpen: (open: boolean) => void;
  currentGroups: [string, PanelConfig][];
  activeGroup?: string;
  setGroup: (value: string | undefined, replace?: boolean | undefined) => void;
  deleteGroup: () => void;
  isAdmin?: boolean;
};
function PanelManagementDialog({
  open,
  setOpen,
  currentGroups,
  activeGroup,
  setGroup,
  deleteGroup,
  isAdmin,
}: PanelManagementDialogProps) {
  const { t } = useTranslation(["components/camera"]);
  const { data: config, mutate: updateConfig } =
    useSWR<FrigateConfig>("config");

  // editing group and state

  const [editingGroupName, setEditingGroupName] = useState("");

  const editingGroup = useMemo(() => {
    if (currentGroups && editingGroupName !== undefined) {
      return currentGroups.find(
        ([groupName]) => groupName === editingGroupName,
      );
    } else {
      return undefined;
    }
  }, [currentGroups, editingGroupName]);

  const [editState, setEditState] = useState<"none" | "add" | "edit">("none");
  const [isLoading, setIsLoading] = useState(false);

  const [, , , deleteGridLayout] = useUserPersistence(
    `${activeGroup}-draggable-layout`,
  );

  useEffect(() => {
    if (!open) {
      setEditState("none");
    }
  }, [open]);

  // callbacks

  const onDeleteGroup = useCallback(
    async (name: string) => {
      deleteGridLayout();
      deleteGroup();

      const isLegacyPanel = !config?.panels?.[name];
      const remainingPanels = currentGroups.filter(
        ([panelName]) => panelName !== name,
      );
      const request = isLegacyPanel
        ? remainingPanels.length === 0
          ? axios.put("config/set?panels=%7B%7D", { requires_restart: 0 })
          : axios.put("config/set", {
              requires_restart: 0,
              config_data: {
                panels: Object.fromEntries(remainingPanels),
              },
            })
        : axios.put(`config/set?panels.${name}`, { requires_restart: 0 });

      await request
        .then((res) => {
          if (res.status === 200) {
            if (activeGroup == name) {
              // deleting current group
              setGroup("default");
            }
            updateConfig();
          } else {
            setOpen(false);
            setEditState("none");
            toast.error(
              t("toast.save.error.title", {
                errorMessage: res.statusText,
                ns: "common",
              }),
              {
                position: "top-center",
              },
            );
          }
        })
        .catch((error) => {
          setOpen(false);
          setEditState("none");
          const errorMessage =
            error.response?.data?.message ||
            error.response?.data?.detail ||
            "Unknown error";
          toast.error(
            t("toast.save.error.title", { errorMessage, ns: "common" }),
            {
              position: "top-center",
            },
          );
        })
        .finally(() => {
          setIsLoading(false);
        });
    },
    [
      updateConfig,
      activeGroup,
      setGroup,
      setOpen,
      deleteGroup,
      deleteGridLayout,
      config,
      currentGroups,
      t,
    ],
  );

  const onSave = () => {
    setOpen(false);
    setEditState("none");
    setEditingGroupName("");
  };

  const onCancel = () => {
    setEditingGroupName("");
    setEditState("none");
  };

  const onEditGroup = useCallback((group: [string, PanelConfig]) => {
    setEditingGroupName(group[0]);
    setEditState("edit");
  }, []);

  const Overlay = isDesktop ? Dialog : MobilePage;
  const Content = isDesktop ? DialogContent : MobilePageContent;
  const Header = isDesktop ? DialogHeader : MobilePageHeader;
  const Description = isDesktop ? DialogDescription : MobilePageDescription;
  const Title = isDesktop ? DialogTitle : MobilePageTitle;

  return (
    <>
      <Toaster
        className="toaster group z-[100]"
        position="top-center"
        closeButton={true}
      />
      <Overlay open={open} onOpenChange={setOpen}>
        <Content
          className={cn(
            "scrollbar-container overflow-y-auto",
            isDesktop && "my-4 flex max-h-dvh w-6/12 flex-col",
            isMobile && "px-4",
          )}
        >
          {editState === "none" && (
            <>
              <Header
                className={cn(isDesktop && "mt-5", "justify-center")}
                onClose={() => setOpen(false)}
              >
                <Title>{t("group.label")}</Title>
                <Description className="sr-only">{t("group.edit")}</Description>
                {isAdmin && (
                  <div
                    className={cn(
                      "absolute",
                      isDesktop && "right-6 top-10",
                      isMobile && "absolute right-0 top-4",
                    )}
                  >
                    <Button
                      size="sm"
                      className={cn(
                        isDesktop &&
                          "size-6 rounded-md bg-secondary-foreground p-1 text-background",
                        isMobile && "text-secondary-foreground",
                      )}
                      aria-label={t("group.add")}
                      onClick={() => {
                        setEditState("add");
                      }}
                    >
                      <LuPlus />
                    </Button>
                  </div>
                )}
              </Header>
              <div className="flex flex-col gap-4 md:gap-3">
                {currentGroups.map((group) => (
                  <PanelRow
                    key={group[0]}
                    group={group}
                    onDeleteGroup={() => onDeleteGroup(group[0])}
                    onEditGroup={() => onEditGroup(group)}
                    isReadOnly={!isAdmin}
                  />
                ))}
              </div>
            </>
          )}

          {editState != "none" && (
            <>
              <Header
                className="mt-2"
                onClose={() => {
                  setEditState("none");
                  setEditingGroupName("");
                }}
              >
                <Title>
                  {editState == "add" ? t("group.add") : t("group.edit")}
                </Title>
                <Description className="sr-only">{t("group.edit")}</Description>
              </Header>
              <PanelEdit
                currentGroups={currentGroups}
                editingGroup={editingGroup}
                isLoading={isLoading}
                setIsLoading={setIsLoading}
                onSave={onSave}
                onCancel={onCancel}
              />
            </>
          )}
        </Content>
      </Overlay>
    </>
  );
}

type EditPanelDialogProps = {
  open: boolean;
  setOpen: (open: boolean) => void;
  currentGroups: [string, PanelConfig][];
  activeGroup?: string;
};
export function EditPanelDialog({
  open,
  setOpen,
  currentGroups,
  activeGroup,
}: EditPanelDialogProps) {
  const { t } = useTranslation(["components/camera"]);
  const Overlay = isDesktop ? Dialog : MobilePage;
  const Content = isDesktop ? DialogContent : MobilePageContent;
  const Header = isDesktop ? DialogHeader : MobilePageHeader;
  const Description = isDesktop ? DialogDescription : MobilePageDescription;
  const Title = isDesktop ? DialogTitle : MobilePageTitle;

  // editing group and state

  const editingGroup = useMemo(() => {
    if (currentGroups && activeGroup) {
      return currentGroups.find(([groupName]) => groupName === activeGroup);
    } else {
      return undefined;
    }
  }, [currentGroups, activeGroup]);

  const [isLoading, setIsLoading] = useState(false);

  return (
    <>
      <Toaster
        className="toaster group z-[100]"
        position="top-center"
        closeButton={true}
      />
      <Overlay
        open={open}
        onOpenChange={(open) => {
          setOpen(open);
        }}
      >
        <Content
          className={cn(
            "min-w-0",
            isDesktop && "max-h-dvh w-6/12 overflow-y-hidden",
          )}
        >
          <div className="scrollbar-container flex flex-col overflow-y-auto md:my-4">
            <Header className="mt-2" onClose={() => setOpen(false)}>
              <Title>{t("group.edit")}</Title>
              <Description className="sr-only">{t("group.edit")}</Description>
            </Header>

            <PanelEdit
              currentGroups={currentGroups}
              editingGroup={editingGroup}
              isLoading={isLoading}
              setIsLoading={setIsLoading}
              onSave={() => setOpen(false)}
              onCancel={() => setOpen(false)}
            />
          </div>
        </Content>
      </Overlay>
    </>
  );
}

type PanelRowProps = {
  group: [string, PanelConfig];
  onDeleteGroup: () => void;
  onEditGroup: () => void;
  isReadOnly?: boolean;
};

export function PanelRow({
  group,
  onDeleteGroup,
  onEditGroup,
  isReadOnly,
}: PanelRowProps) {
  const { t } = useTranslation(["components/camera"]);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  if (!group) {
    return;
  }

  return (
    <>
      <div
        key={group[0]}
        className="transition-background flex flex-row items-center justify-between rounded-lg duration-100 md:p-1"
      >
        <div className={`flex items-center`}>
          <p className="cursor-default">{group[0]}</p>
        </div>
        <AlertDialog
          open={deleteDialogOpen}
          onOpenChange={() => setDeleteDialogOpen(!deleteDialogOpen)}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>
                {t("group.delete.confirm.title")}
              </AlertDialogTitle>
            </AlertDialogHeader>
            <AlertDialogDescription>
              <Trans ns="components/camera" values={{ name: group[0] }}>
                group.delete.confirm.desc
              </Trans>
            </AlertDialogDescription>
            <AlertDialogFooter>
              <AlertDialogCancel>
                {t("button.cancel", { ns: "common" })}
              </AlertDialogCancel>
              <AlertDialogAction
                className={buttonVariants({ variant: "destructive" })}
                onClick={onDeleteGroup}
              >
                {t("button.delete", { ns: "common" })}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        {isMobile && !isReadOnly && (
          <>
            <DropdownMenu>
              <DropdownMenuTrigger>
                <HiOutlineDotsVertical className="size-5" />
              </DropdownMenuTrigger>
              <DropdownMenuPortal>
                <DropdownMenuContent>
                  <DropdownMenuItem
                    aria-label={t("group.edit")}
                    onClick={onEditGroup}
                  >
                    {t("button.edit", { ns: "common" })}
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    aria-label={t("group.delete.label")}
                    onClick={() => setDeleteDialogOpen(true)}
                  >
                    {t("button.delete", { ns: "common" })}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenuPortal>
            </DropdownMenu>
          </>
        )}
        {!isMobile && !isReadOnly && (
          <div className="flex flex-row items-center gap-2">
            <Tooltip>
              <TooltipTrigger asChild>
                <IconWrapper
                  icon={LuPencil}
                  className={`size-[15px] cursor-pointer`}
                  onClick={onEditGroup}
                />
              </TooltipTrigger>
              <TooltipContent>
                {t("button.edit", { ns: "common" })}
              </TooltipContent>
            </Tooltip>

            <Tooltip>
              <TooltipTrigger asChild>
                <IconWrapper
                  icon={HiTrash}
                  className={`size-[15px] cursor-pointer`}
                  onClick={() => setDeleteDialogOpen(true)}
                />
              </TooltipTrigger>
              <TooltipContent>
                {t("button.delete", { ns: "common" })}
              </TooltipContent>
            </Tooltip>
          </div>
        )}
      </div>
    </>
  );
}

type PanelEditProps = {
  currentGroups: [string, PanelConfig][];
  editingGroup?: [string, PanelConfig];
  isLoading: boolean;
  setIsLoading: React.Dispatch<React.SetStateAction<boolean>>;
  onSave?: () => void;
  onCancel?: () => void;
};

export function PanelEdit({
  currentGroups,
  editingGroup,
  isLoading,
  setIsLoading,
  onSave,
  onCancel,
}: PanelEditProps) {
  const { t } = useTranslation(["components/camera"]);
  const { data: config, mutate: updateConfig } =
    useSWR<FrigateConfig>("config");

  const { allGroupsStreamingSettings, setAllGroupsStreamingSettings } =
    useStreamingSettings();

  const [groupStreamingSettings, setGroupStreamingSettings] =
    useState<GroupStreamingSettings>(
      allGroupsStreamingSettings[editingGroup?.[0] ?? ""],
    );

  const allowedCameras = useAllowedCameras();
  const hasFullCameraAccess = useHasFullCameraAccess();

  const [openCamera, setOpenCamera] = useState<string | null>();
  const [editingTileId, setEditingTileId] = useState<string | null>(null);

  const birdseyeConfig = useMemo(() => config?.birdseye, [config]);

  const formSchema = z.object({
    name: z
      .string()
      .trim()
      .min(2, {
        message: t("group.name.errorMessage.mustLeastCharacters"),
      })
      .transform((val: string) => val.replace(/\s+/g, "_"))
      .refine(
        (value: string) => {
          return (
            editingGroup !== undefined ||
            !currentGroups.map((group) => group[0]).includes(value)
          );
        },
        {
          message: t("group.name.errorMessage.exists"),
        },
      )
      .refine(
        (value: string) => {
          return !value.includes(".");
        },
        {
          message: t("group.name.errorMessage.nameMustNotPeriod"),
        },
      )
      .refine((value: string) => value.toLowerCase() !== "default", {
        message: t("group.name.errorMessage.invalid"),
      }),

    tiles: z.array(
      z.object({
        id: z.string(),
        camera: z.string(),
        crop: z.tuple([z.number(), z.number(), z.number(), z.number()]),
      }),
    ),
    icon: z
      .string()
      .min(1, { message: "You must select an icon." })
      .refine((value) => Object.keys(LuIcons).includes(value), {
        message: "Invalid icon",
      }),
  });

  const onSubmit = useCallback(
    async (values: z.infer<typeof formSchema>) => {
      if (!values) {
        return;
      }

      setIsLoading(true);

      // update streaming settings
      const updatedSettings: AllGroupsStreamingSettings = {
        ...Object.fromEntries(
          Object.entries(allGroupsStreamingSettings || {}).filter(
            ([key]) => key !== editingGroup?.[0],
          ),
        ),
        [values.name]: groupStreamingSettings,
      };

      const order =
        editingGroup === undefined
          ? currentGroups.length + 1
          : editingGroup[1].order;

      const panelConfig: PanelConfig = {
        order,
        icon: values.icon as IconName,
        tiles: values.tiles,
      };
      const migratingPanels = currentGroups.filter(
        ([panelName]) =>
          !editingGroup ||
          editingGroup[0] === values.name ||
          panelName !== editingGroup[0],
      );
      const panels: Record<string, PanelConfig | null> = {
        ...(config?.panels == null ? Object.fromEntries(migratingPanels) : {}),
        [values.name]: panelConfig,
      };
      if (
        editingGroup &&
        editingGroup[0] !== values.name &&
        config?.panels?.[editingGroup[0]]
      ) {
        panels[editingGroup[0]] = null;
      }

      axios
        .put("config/set", {
          requires_restart: 0,
          config_data: { panels },
        })
        .then(async (res) => {
          if (res.status === 200) {
            toast.success(
              t("group.success", {
                name: values.name,
              }),
              {
                position: "top-center",
              },
            );
            updateConfig();
            if (onSave) {
              onSave();
            }
            setAllGroupsStreamingSettings(updatedSettings);
          } else {
            toast.error(
              t("toast.save.error.title", {
                errorMessage: res.statusText,
                ns: "common",
              }),
              {
                position: "top-center",
              },
            );
          }
        })
        .catch((error) => {
          const errorMessage =
            error.response?.data?.message ||
            error.response?.data?.detail ||
            "Unknown error";
          toast.error(
            t("toast.save.error.title", {
              errorMessage,
              ns: "common",
            }),
            { position: "top-center" },
          );
        })
        .finally(() => {
          setIsLoading(false);
        });
    },
    [
      currentGroups,
      setIsLoading,
      onSave,
      updateConfig,
      editingGroup,
      groupStreamingSettings,
      allGroupsStreamingSettings,
      setAllGroupsStreamingSettings,
      config,
      t,
    ],
  );

  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    mode: "onSubmit",
    defaultValues: {
      name: (editingGroup && editingGroup[0]) ?? "",
      icon: editingGroup && (editingGroup[1].icon as IconName),
      tiles: editingGroup?.[1].tiles ?? [],
    },
  });

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="mt-2 space-y-6 overflow-y-hidden"
      >
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("group.name.label")}</FormLabel>
              <FormControl>
                <Input
                  className="w-full border border-input bg-background p-2 hover:bg-accent hover:text-accent-foreground dark:[color-scheme:dark]"
                  placeholder={t("group.name.placeholder")}
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <Separator className="my-2 flex bg-secondary" />
        <div className="scrollbar-container max-h-[40dvh] overflow-y-auto">
          <FormField
            control={form.control}
            name="tiles"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t("group.cameras.label")}</FormLabel>
                <FormDescription>{t("group.cameras.desc")}</FormDescription>
                <FormMessage />
                {[
                  ...(birdseyeConfig?.enabled && hasFullCameraAccess
                    ? ["birdseye"]
                    : []),
                  ...Object.keys(config?.cameras ?? {})
                    .filter((camera) => allowedCameras.includes(camera))
                    .sort(
                      (a, b) =>
                        (config?.cameras[a]?.ui?.order ?? 0) -
                        (config?.cameras[b]?.ui?.order ?? 0),
                    ),
                ].map((camera) => {
                  const cameraTiles = (field.value ?? []).filter(
                    (tile) => tile.camera === camera,
                  );
                  return (
                    <FormControl key={camera}>
                      <div>
                        <div className="flex min-h-10 items-center justify-between gap-1">
                          <CameraNameLabel
                            className="mx-2 w-full text-primary smart-capitalize"
                            htmlFor={camera.replaceAll("_", " ")}
                            camera={camera}
                          />

                          <div className="flex items-center gap-x-2">
                            {camera !== "birdseye" && (
                              <Dialog
                                open={openCamera === camera}
                                onOpenChange={(isOpen) =>
                                  setOpenCamera(isOpen ? camera : null)
                                }
                              >
                                <DialogTrigger asChild>
                                  <Button
                                    className="flex h-auto items-center gap-1"
                                    aria-label={t("group.camera.setting.label")}
                                    size="icon"
                                    variant="ghost"
                                    disabled={cameraTiles.length === 0}
                                  >
                                    <LuIcons.LuSettings
                                      className={cn(
                                        cameraTiles.length > 0
                                          ? "text-primary"
                                          : "text-muted-foreground",
                                        "size-5",
                                      )}
                                    />
                                  </Button>
                                </DialogTrigger>
                                <CameraStreamingDialog
                                  camera={camera}
                                  groupStreamingSettings={
                                    groupStreamingSettings
                                  }
                                  setGroupStreamingSettings={
                                    setGroupStreamingSettings
                                  }
                                  setIsDialogOpen={(isOpen) =>
                                    setOpenCamera(isOpen ? camera : null)
                                  }
                                />
                              </Dialog>
                            )}
                            <Button
                              type="button"
                              size="icon"
                              variant="ghost"
                              disabled={cameraTiles.length === 0}
                              aria-label={t("group.camera.removeTile")}
                              onClick={() => {
                                const lastTile = cameraTiles.at(-1);
                                field.onChange(
                                  (field.value ?? []).filter(
                                    (tile) => tile.id !== lastTile?.id,
                                  ),
                                );
                              }}
                            >
                              <LuIcons.LuMinus className="size-4" />
                            </Button>
                            <span
                              className="w-6 text-center text-sm tabular-nums"
                              aria-label={`${t("group.camera.tileCount")}: ${cameraTiles.length}`}
                            >
                              {cameraTiles.length}
                            </span>
                            <Button
                              type="button"
                              size="icon"
                              variant="ghost"
                              aria-label={t("group.camera.addTile")}
                              onClick={() => {
                                const tile: PanelTileConfig = {
                                  id: `${camera}-${crypto.randomUUID()}`,
                                  camera,
                                  crop: [0, 0, 1, 1],
                                };
                                field.onChange([...(field.value ?? []), tile]);
                              }}
                            >
                              <LuIcons.LuPlus className="size-4" />
                            </Button>
                          </div>
                        </div>
                        {cameraTiles.map((tile, index) => (
                          <div
                            key={tile.id}
                            className="ml-8 flex min-h-9 items-center justify-between border-l border-secondary pl-3"
                          >
                            <span className="text-sm text-muted-foreground">
                              {t("group.camera.tileLabel", {
                                number: index + 1,
                              })}
                            </span>
                            <div className="flex items-center gap-1">
                              {camera !== "birdseye" && (
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => setEditingTileId(tile.id)}
                                >
                                  <LuIcons.LuScan className="mr-2 size-4" />
                                  {t("group.camera.crop.label")}
                                </Button>
                              )}
                              <Button
                                type="button"
                                size="icon"
                                variant="ghost"
                                aria-label={t("group.camera.removeTile")}
                                onClick={() =>
                                  field.onChange(
                                    (field.value ?? []).filter(
                                      (candidate) => candidate.id !== tile.id,
                                    ),
                                  )
                                }
                              >
                                <HiTrash className="size-4" />
                              </Button>
                            </div>
                            <PanelTileCropDialog
                              open={editingTileId === tile.id}
                              setOpen={(open) =>
                                setEditingTileId(open ? tile.id : null)
                              }
                              tile={tile}
                              onChange={(updatedTile) =>
                                field.onChange(
                                  (field.value ?? []).map((candidate) =>
                                    candidate.id === updatedTile.id
                                      ? updatedTile
                                      : candidate,
                                  ),
                                )
                              }
                            />
                          </div>
                        ))}
                      </div>
                    </FormControl>
                  );
                })}
              </FormItem>
            )}
          />
        </div>

        <Separator className="my-2 flex bg-secondary" />
        <FormField
          control={form.control}
          name="icon"
          render={({ field }) => (
            <FormItem className="flex flex-col space-y-2">
              <FormLabel>{t("group.icon")}</FormLabel>
              <FormControl>
                <IconPicker
                  selectedIcon={{
                    name: field.value,
                    Icon: field.value
                      ? LuIcons[field.value as IconName]
                      : undefined,
                  }}
                  setSelectedIcon={(newIcon) => {
                    field.onChange(newIcon?.name ?? undefined);
                  }}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <Separator className="my-2 flex bg-secondary" />

        <DialogFooter className="py-5 md:pb-0">
          <Button
            type="button"
            aria-label={t("button.cancel", { ns: "common" })}
            onClick={onCancel}
          >
            {t("button.cancel", { ns: "common" })}
          </Button>
          <Button
            variant="select"
            disabled={isLoading}
            aria-label={t("button.save", { ns: "common" })}
            type="submit"
          >
            {isLoading ? (
              <div className="flex flex-row items-center gap-2">
                <ActivityIndicator className="size-4" />
                <span>{t("button.saving", { ns: "common" })}</span>
              </div>
            ) : (
              t("button.save", { ns: "common" })
            )}
          </Button>
        </DialogFooter>
      </form>
    </Form>
  );
}

type PanelTileCropDialogProps = {
  open: boolean;
  setOpen: (open: boolean) => void;
  tile: PanelTileConfig;
  onChange: (tile: PanelTileConfig) => void;
};

function PanelTileCropDialog({
  open,
  setOpen,
  tile,
  onChange,
}: PanelTileCropDialogProps) {
  const { t } = useTranslation(["components/camera"]);
  const [left, top, right, bottom] = tile.crop;
  const cropWidth = right - left;
  const cropHeight = bottom - top;
  const zoom = 1 / cropWidth;
  const centerX = left + cropWidth / 2;
  const centerY = top + cropHeight / 2;

  const updateCrop = useCallback(
    (nextZoom: number, nextCenterX: number, nextCenterY: number) => {
      const width = 1 / nextZoom;
      const height = 1 / nextZoom;
      const halfWidth = width / 2;
      const halfHeight = height / 2;
      const clampedCenterX = Math.min(
        1 - halfWidth,
        Math.max(halfWidth, nextCenterX),
      );
      const clampedCenterY = Math.min(
        1 - halfHeight,
        Math.max(halfHeight, nextCenterY),
      );

      onChange({
        ...tile,
        crop: [
          clampedCenterX - halfWidth,
          clampedCenterY - halfHeight,
          clampedCenterX + halfWidth,
          clampedCenterY + halfHeight,
        ],
      });
    },
    [onChange, tile],
  );

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("group.camera.crop.title")}</DialogTitle>
          <DialogDescription>{t("group.camera.crop.desc")}</DialogDescription>
        </DialogHeader>

        <div className="relative aspect-video overflow-hidden rounded-lg bg-black">
          <div
            className="absolute"
            style={{
              left: `${(-left / cropWidth) * 100}%`,
              top: `${(-top / cropHeight) * 100}%`,
              width: `${100 / cropWidth}%`,
              height: `${100 / cropHeight}%`,
            }}
          >
            <AutoUpdatingCameraImage
              camera={tile.camera}
              className="size-full"
              cameraClasses="size-full object-cover"
              reloadInterval={1000}
              showFps={false}
            />
          </div>
        </div>

        <div className="space-y-5">
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span>{t("group.camera.crop.zoom")}</span>
              <span className="tabular-nums">{zoom.toFixed(1)}×</span>
            </div>
            <Slider
              min={1}
              max={8}
              step={0.1}
              value={[zoom]}
              onValueChange={([value]) => updateCrop(value, centerX, centerY)}
            />
          </div>

          <div className="space-y-2">
            <span className="text-sm">{t("group.camera.crop.horizontal")}</span>
            <Slider
              min={cropWidth / 2}
              max={1 - cropWidth / 2}
              step={0.01}
              disabled={zoom === 1}
              value={[centerX]}
              onValueChange={([value]) => updateCrop(zoom, value, centerY)}
            />
          </div>

          <div className="space-y-2">
            <span className="text-sm">{t("group.camera.crop.vertical")}</span>
            <Slider
              min={cropHeight / 2}
              max={1 - cropHeight / 2}
              step={0.01}
              disabled={zoom === 1}
              value={[centerY]}
              onValueChange={([value]) => updateCrop(zoom, centerX, value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="ghost"
            onClick={() => updateCrop(1, 0.5, 0.5)}
          >
            {t("group.camera.crop.reset")}
          </Button>
          <Button type="button" onClick={() => setOpen(false)}>
            {t("button.done", { ns: "common" })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
