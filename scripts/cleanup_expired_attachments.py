from services.supabase import (
    delete_attachment_object,
    get_expired_attachments,
    purge_attachment_record,
)


def main():
    expired = get_expired_attachments()
    for attachment in expired:
        delete_attachment_object(attachment["storage_path"])
        purge_attachment_record(attachment["id"])
    print(f"Cleaned {len(expired)} expired attachments.")


if __name__ == "__main__":
    main()
