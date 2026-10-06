static ssize_t re_read(struct file *file,
                       char __user *user_buffer,
                       size_t count,
                       loff_t *offset)
{
    u8 *tmp;
    size_t total = 0;
    size_t available;

    if (*offset < 0)
        return -EINVAL;

    if ((u64)*offset >= phys_size)
        return 0;

    available = phys_size - (size_t)*offset;

    if (count > available)
        count = available;

    if (!count)
        return 0;

    tmp = kmalloc(PAGE_SIZE, GFP_KERNEL);
    if (!tmp)
        return -ENOMEM;

    while (total < count) {
        phys_addr_t current;
        size_t page_remaining;
        size_t chunk;
        int ret;

        current = phys_base +
                  (phys_addr_t)*offset +
                  total;

        page_remaining =
            PAGE_SIZE - offset_in_page(current);

        chunk = count - total;

        if (chunk > page_remaining)
            chunk = page_remaining;

        ret = read_phys_ram(current,
                            tmp,
                            chunk);

        if (ret) {
            kfree(tmp);

            if (total) {
                *offset += total;
                return total;
            }

            return ret;
        }

        if (copy_to_user(user_buffer + total,
                         tmp,
                         chunk)) {
            kfree(tmp);

            if (total) {
                *offset += total;
                return total;
            }

            return -EFAULT;
        }

        total += chunk;
    }

    kfree(tmp);

    *offset += total;

    return total;
}

// that is the read one

static loff_t re_llseek(struct file *file,
                        loff_t offset,
                        int whence)
{
    return fixed_size_llseek(file,
                             offset,
                             whence,
                             phys_size);
}

// that is the llseek

