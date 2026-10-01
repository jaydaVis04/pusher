#for the readin
static ssize_t re_read(struct file *file,
                       char __user *user_buffer,
                       size_t count,
                       loff_t *offset)
{
    unsigned char *tmp;
    size_t total = 0;
    size_t chunk;

    if (!ching_chong)
        return -ENODEV;

    if (*offset < 0)
        return -EINVAL;

    if (*offset >= BUFFER_SIZE)
        return 0;

    if (count > BUFFER_SIZE - *offset)
        count = BUFFER_SIZE - *offset;

    tmp = kmalloc(PAGE_SIZE, GFP_KERNEL);
    if (!tmp)
        return -ENOMEM;

    while (total < count) {
        chunk = min_t(size_t, PAGE_SIZE, count - total);

        memcpy_fromio(
            tmp,
            (u8 __iomem *)ching_chong + *offset + total,
            chunk
        );

        if (copy_to_user(user_buffer + total, tmp, chunk)) {
            kfree(tmp);
            return total ? total : -EFAULT;
        }

        total += chunk;
    }

    *offset += total;

    pr_info_ratelimited(
        "re_mem: READ offset=0x%llx bytes=%zu\n",
        (unsigned long long)(*offset - total),
        total
    );

    kfree(tmp);
    return total;
}

# this is for the writing now

static ssize_t re_write(struct file *file,
                        const char __user *user_buffer,
                        size_t count,
                        loff_t *offset)
{
    unsigned char *tmp;
    size_t total = 0;
    size_t chunk;

    if (!ching_chong)
        return -ENODEV;

    if (*offset < 0)
        return -EINVAL;

    if (*offset >= BUFFER_SIZE)
        return -ENOSPC;

    if (count > BUFFER_SIZE - *offset)
        count = BUFFER_SIZE - *offset;

    tmp = kmalloc(PAGE_SIZE, GFP_KERNEL);
    if (!tmp)
        return -ENOMEM;

    while (total < count) {
        chunk = min_t(size_t, PAGE_SIZE, count - total);

        if (copy_from_user(tmp,
                           user_buffer + total,
                           chunk)) {
            kfree(tmp);
            return total ? total : -EFAULT;
        }

        memcpy_toio(
            (u8 __iomem *)ching_chong + *offset + total,
            tmp,
            chunk
        );

        total += chunk;
    }

    *offset += total;

    pr_info_ratelimited(
        "re_mem: WRITE offset=0x%llx bytes=%zu\n",
        (unsigned long long)(*offset - total),
        total
    );

    kfree(tmp);
    return total;
}

