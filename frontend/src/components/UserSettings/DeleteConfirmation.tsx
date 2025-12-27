import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { LoadingButton } from "@/components/ui/loading-button"
import { useMemberCancellation } from "@/hooks/useMemberCancellation"

const DeleteConfirmation = () => {
  const { info, apply, cancel, isApplying, isCanceling, isLoading } = useMemberCancellation('desktop');

  // Status check: 0 or 1 usually implies pending/audit in Niushop logic
  const isPending = info && (info.status === 0 || info.status === 1);

  const handleAction = () => {
    if (isPending) {
      cancel(undefined, {
        onSuccess: () => {
          // Close dialog? automated by query invalidation re-rendering state
        }
      });
    } else {
      apply();
    }
  }

  if (isLoading) return <Button disabled variant="outline">Loading...</Button>;

  if (isPending) {
    return (
      <div className="mt-3">
        <p className="text-sm text-yellow-600 mb-2">
          Cancellation request is pending review.
        </p>
        <Dialog>
          <DialogTrigger asChild>
            <Button variant="outline" className="border-red-200 text-red-600 hover:bg-red-50">
              Withdraw Request
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Withdraw Cancellation?</DialogTitle>
              <DialogDescription>
                You can withdraw your account deletion request and continue using the service.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter className="mt-4">
              <DialogClose asChild>
                <Button variant="outline">Cancel</Button>
              </DialogClose>
              <LoadingButton
                variant="default"
                onClick={handleAction}
                loading={isCanceling}
              >
                Confirm Withdraw
              </LoadingButton>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    )
  }

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="destructive" className="mt-3">
          Delete Account
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete Account?</DialogTitle>
          <DialogDescription>
            This will submit a request to <strong>permanently delete your account</strong>.
            <br /><br />
            This process may require administrator approval. Once approved, all your data will be removed.
          </DialogDescription>
        </DialogHeader>

        <DialogFooter className="mt-4">
          <DialogClose asChild>
            <Button variant="outline">
              Cancel
            </Button>
          </DialogClose>
          <LoadingButton
            variant="destructive"
            onClick={handleAction}
            loading={isApplying}
          >
            Apply for Deletion
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default DeleteConfirmation
