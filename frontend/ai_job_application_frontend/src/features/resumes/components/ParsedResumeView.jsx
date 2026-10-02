function dates(start, end) {
  return [start, end].filter(Boolean).join(' – ')
}

function Section({ title, children }) {
  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      {children}
    </section>
  )
}

/** The structured resume the AI extracted (skills, experience, education …). */
export function ParsedResumeView({ parsed }) {
  const contact = [parsed.email, parsed.phone, parsed.location, ...parsed.links].filter(Boolean)
  return (
    <div className="space-y-5">
      <div>
        <p className="text-lg font-semibold">{parsed.name ?? 'Unnamed'}</p>
        {parsed.headline && <p className="text-sm">{parsed.headline}</p>}
        {contact.length > 0 && (
          <p className="text-sm text-muted-foreground">{contact.join(' · ')}</p>
        )}
      </div>

      {parsed.summary && (
        <Section title="Summary">
          <p className="text-sm">{parsed.summary}</p>
        </Section>
      )}

      {parsed.skills.length > 0 && (
        <Section title="Skills">
          <div className="flex flex-wrap gap-1.5">
            {parsed.skills.map((skill) => (
              <span key={skill} className="rounded-md bg-secondary px-2 py-0.5 text-xs">
                {skill}
              </span>
            ))}
          </div>
        </Section>
      )}

      {parsed.experience.length > 0 && (
        <Section title="Experience">
          <ul className="space-y-4">
            {parsed.experience.map((job, index) => (
              <li key={`${job.company}-${index}`}>
                <div className="flex flex-wrap justify-between gap-x-4 text-sm">
                  <span>
                    <span className="font-medium">{job.title}</span> · {job.company}
                    {job.location ? `, ${job.location}` : ''}
                  </span>
                  <span className="text-muted-foreground">{dates(job.start, job.end)}</span>
                </div>
                {job.highlights.length > 0 && (
                  <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">
                    {job.highlights.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {parsed.projects.length > 0 && (
        <Section title="Projects">
          <ul className="space-y-2 text-sm">
            {parsed.projects.map((project) => (
              <li key={project.name}>
                <span className="font-medium">{project.name}</span>
                {project.technologies.length > 0 && (
                  <span className="text-muted-foreground">
                    {' '}
                    ({project.technologies.join(', ')})
                  </span>
                )}
                <p>{project.description}</p>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {parsed.education.length > 0 && (
        <Section title="Education">
          <ul className="space-y-2 text-sm">
            {parsed.education.map((school, index) => (
              <li
                key={`${school.institution}-${index}`}
                className="flex flex-wrap justify-between gap-x-4"
              >
                <span>
                  <span className="font-medium">{school.degree}</span> · {school.institution}
                  {school.details ? ` — ${school.details}` : ''}
                </span>
                <span className="text-muted-foreground">{dates(school.start, school.end)}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {parsed.certifications.length > 0 && (
        <Section title="Certifications">
          <ul className="list-disc pl-5 text-sm">
            {parsed.certifications.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  )
}
