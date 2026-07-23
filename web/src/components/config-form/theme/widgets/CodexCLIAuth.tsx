import { useEffect, useRef, useState } from "react";
import axios from "axios";
import useSWR from "swr";
import {
  CheckCircle2,
  Copy,
  ExternalLink,
  LogIn,
  LogOut,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import ActivityIndicator from "@/components/indicators/activity-indicator";
import { Button } from "@/components/ui/button";

type CodexAuthStatus = {
  status: "starting" | "pending" | "signed_in" | "signed_out" | "error";
  auth_type?: string;
  plan_type?: string;
  verification_url?: string;
  user_code?: string;
  message?: string;
};

type CodexCLIAuthProps = {
  providerKey: string;
  onAuthenticated: () => void;
};

export function CodexCLIAuth({
  providerKey,
  onAuthenticated,
}: CodexCLIAuthProps) {
  const { t } = useTranslation(["views/settings", "common"]);
  const [busy, setBusy] = useState(false);
  const previousStatus = useRef<CodexAuthStatus["status"] | undefined>(
    undefined,
  );
  const endpoint = `genai/codex/auth?name=${encodeURIComponent(providerKey)}`;
  const { data, error, isLoading, mutate } = useSWR<CodexAuthStatus>(endpoint, {
    revalidateOnFocus: false,
    refreshInterval: (latest) => (latest?.status === "pending" ? 2000 : 0),
  });

  useEffect(() => {
    if (data?.status === "signed_in" && previousStatus.current === "pending") {
      onAuthenticated();
      toast.success(
        t("configForm.codexAuth.signInComplete", {
          ns: "views/settings",
          defaultValue: "Signed in with ChatGPT",
        }),
      );
    }
    previousStatus.current = data?.status;
  }, [data?.status, onAuthenticated, t]);

  const postAction = async (action: "login" | "cancel" | "logout") => {
    setBusy(true);
    try {
      const response = await axios.post<CodexAuthStatus>(
        `genai/codex/auth/${action}?name=${encodeURIComponent(providerKey)}`,
      );
      await mutate(response.data, false);
      if (action === "logout") {
        onAuthenticated();
        toast.success(
          t("configForm.codexAuth.signOutComplete", {
            ns: "views/settings",
            defaultValue: "Signed out of ChatGPT",
          }),
        );
      }
    } catch (requestError) {
      const message = axios.isAxiosError(requestError)
        ? requestError.response?.data?.message
        : undefined;
      toast.error(
        message ||
          t("configForm.codexAuth.actionFailed", {
            ns: "views/settings",
            defaultValue: "Unable to update ChatGPT sign in",
          }),
      );
    } finally {
      setBusy(false);
    }
  };

  const copyCode = async () => {
    if (!data?.user_code) return;
    await navigator.clipboard.writeText(data.user_code);
    toast.success(
      t("configForm.codexAuth.codeCopied", {
        ns: "views/settings",
        defaultValue: "Sign-in code copied",
      }),
    );
  };

  if (isLoading) {
    return (
      <div className="mt-2 flex items-center gap-2 rounded-lg border border-secondary-highlight bg-background_alt p-3 text-sm text-muted-foreground">
        <ActivityIndicator className="size-4" size={16} />
        {t("configForm.codexAuth.checking", {
          ns: "views/settings",
          defaultValue: "Checking ChatGPT sign in…",
        })}
      </div>
    );
  }

  if (error) {
    return (
      <div className="mt-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
        {t("configForm.codexAuth.statusFailed", {
          ns: "views/settings",
          defaultValue: "Unable to check ChatGPT sign-in status",
        })}
      </div>
    );
  }

  if (data?.status === "pending") {
    return (
      <div className="mt-2 space-y-3 rounded-lg border border-secondary-highlight bg-background_alt p-3">
        <div>
          <div className="text-sm font-medium">
            {t("configForm.codexAuth.finishSignIn", {
              ns: "views/settings",
              defaultValue: "Finish signing in with ChatGPT",
            })}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {t("configForm.codexAuth.enterCode", {
              ns: "views/settings",
              defaultValue:
                "Open ChatGPT, sign in to your account, then enter this one-time code.",
            })}
          </div>
        </div>
        <button
          type="button"
          onClick={copyCode}
          className="flex w-full items-center justify-between rounded-md border border-secondary-highlight bg-background px-3 py-2 font-mono text-base tracking-wider hover:bg-secondary"
          aria-label={t("configForm.codexAuth.copyCode", {
            ns: "views/settings",
            defaultValue: "Copy sign-in code",
          })}
        >
          <span>{data.user_code}</span>
          <Copy className="size-4 text-muted-foreground" />
        </button>
        <div className="flex flex-wrap gap-2">
          {data.verification_url && (
            <Button asChild type="button" size="sm">
              <a
                href={data.verification_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {t("configForm.codexAuth.openChatGPT", {
                  ns: "views/settings",
                  defaultValue: "Open ChatGPT",
                })}
                <ExternalLink className="ml-2 size-4" />
              </a>
            </Button>
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() => postAction("cancel")}
          >
            <X className="mr-2 size-4" />
            {t("button.cancel", { ns: "common" })}
          </Button>
        </div>
      </div>
    );
  }

  if (data?.status === "signed_in") {
    const plan = data.plan_type
      ? data.plan_type.replaceAll("_", " ")
      : undefined;
    return (
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-secondary-highlight bg-background_alt p-3">
        <div className="flex min-w-0 items-center gap-2">
          <CheckCircle2 className="size-5 shrink-0 text-success" />
          <div className="min-w-0">
            <div className="text-sm font-medium">
              {t("configForm.codexAuth.signedIn", {
                ns: "views/settings",
                defaultValue: "Signed in with ChatGPT",
              })}
            </div>
            {plan && (
              <div className="truncate text-xs capitalize text-muted-foreground">
                {t("configForm.codexAuth.subscription", {
                  ns: "views/settings",
                  plan,
                  defaultValue: "{{plan}} subscription",
                })}
              </div>
            )}
          </div>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={() => postAction("logout")}
        >
          {busy ? (
            <ActivityIndicator className="mr-2 size-4" size={16} />
          ) : (
            <LogOut className="mr-2 size-4" />
          )}
          {t("configForm.codexAuth.signOut", {
            ns: "views/settings",
            defaultValue: "Sign out",
          })}
        </Button>
      </div>
    );
  }

  return (
    <div className="mt-2 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-secondary-highlight bg-background_alt p-3">
      <div>
        <div className="text-sm font-medium">
          {t("configForm.codexAuth.notSignedIn", {
            ns: "views/settings",
            defaultValue: "ChatGPT is not signed in",
          })}
        </div>
        <div className="mt-1 text-xs text-muted-foreground">
          {data?.message ||
            t("configForm.codexAuth.signInDesc", {
              ns: "views/settings",
              defaultValue:
                "Use a ChatGPT subscription for Codex-powered descriptions and chat.",
            })}
        </div>
      </div>
      <Button
        type="button"
        size="sm"
        disabled={busy}
        onClick={() => postAction("login")}
      >
        {busy ? (
          <ActivityIndicator className="mr-2 size-4" size={16} />
        ) : (
          <LogIn className="mr-2 size-4" />
        )}
        {t("configForm.codexAuth.signIn", {
          ns: "views/settings",
          defaultValue: "Sign in with ChatGPT",
        })}
      </Button>
    </div>
  );
}
