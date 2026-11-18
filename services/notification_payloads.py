def submission_payload(application):
    return {
        "application_id": application.id, "kind": application.kind.value,
        "pet_name": application.pet_name, "district": application.district,
        "description": application.description, "additional_info": application.additional_info,
        "photo_ids": list(application.photo_ids or (application.photo_id,)),
        "author_id": application.user_id,
    }
